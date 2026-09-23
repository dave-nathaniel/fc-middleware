import os
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import InventoryTransaction, Dispatch
from . import posting, dispatch as dispatching

logger = logging.getLogger(__name__)

MAX_RETRIES = int(os.getenv("POS_MAX_RETRIES", "6"))
# Seconds before retry n: 60, 120, 240 ... capped at 30 minutes.
BACKOFF_CAP = 1800
# A record untouched for this long in "queued"/"posting", or an invoice still pending, is re-queued.
STALE_AFTER = timedelta(minutes=int(os.getenv("POS_STALE_MINUTES", "30")))


def _countdown(retries):
	return min(60 * (2 ** retries), BACKOFF_CAP)


@shared_task(bind=True, max_retries=MAX_RETRIES)
def post_transaction(self, txn_id):
	"""Posts a POS GRN, return or wastage to ByD, retrying with backoff on failure."""
	# Claim the record so an admin retry and a scheduled retry never post it at the same time.
	claimed = InventoryTransaction.objects.filter(
		pk=txn_id, status__in=[InventoryTransaction.QUEUED, InventoryTransaction.FAILED]
	).update(status=InventoryTransaction.POSTING)
	if not claimed:
		return
	txn = InventoryTransaction.objects.select_related("store", "dispatch", "purchase_order").get(pk=txn_id)
	txn.attempts += 1
	txn.save(update_fields=["attempts"])
	try:
		posting.post(txn)
	except posting.PostingError as e:
		# Our data is wrong, or the outcome in ByD is unknown: a person has to look.
		_record_error(txn, str(e), InventoryTransaction.FAILED)
	except Exception as e:
		final = self.request.retries >= self.max_retries
		_record_error(txn, str(e), InventoryTransaction.FAILED if final else InventoryTransaction.QUEUED)
		if not final:
			raise self.retry(exc=e, countdown=_countdown(self.request.retries))


def _record_error(txn, error, status):
	logger.error(f"{txn}: {error}")
	txn.status = status
	txn.error = error[:4000]
	txn.save(update_fields=["status", "error"])


@shared_task(bind=True, max_retries=MAX_RETRIES)
def send_dispatch(self, dispatch_id):
	"""Sends one invoice to Restroworks."""
	dispatch = Dispatch.objects.select_related("purchase_order__store").get(pk=dispatch_id)
	if dispatch.status == Dispatch.SENT:
		return
	try:
		dispatching.send(dispatch)
	except Exception as e:
		logger.error(f"Invoice {dispatch.invoice_no}: {e}")
		if self.request.retries < self.max_retries:
			raise self.retry(exc=e, countdown=_countdown(self.request.retries))


@shared_task
def sync_dispatches():
	"""Periodic: create invoices for ByD documents that are now due, send them, and pick up stragglers."""
	for new_dispatch in dispatching.build_dispatches():
		send_dispatch.delay(new_dispatch.pk)
	requeue_stale()


def requeue_stale():
	"""
		Catches work whose Celery message was never sent (broker down at the time)
		or was lost (worker killed mid-task).
	"""
	cutoff = timezone.now() - STALE_AFTER
	stale = InventoryTransaction.objects.filter(
		status__in=[InventoryTransaction.QUEUED, InventoryTransaction.POSTING], updated_at__lt=cutoff
	)
	for txn in stale:
		if txn.status == InventoryTransaction.POSTING and txn.kind == InventoryTransaction.WASTAGE:
			# The consumption may have reached ByD; resending could post it twice.
			_record_error(txn, f"Posting was interrupted. Check ByD for goods movement external ID {txn.byd_document_id} before using 'Retry posting'.", InventoryTransaction.FAILED)
			continue
		# Inbound deliveries are safe to resume: the task looks the document up by its ID first.
		InventoryTransaction.objects.filter(pk=txn.pk).update(status=InventoryTransaction.QUEUED, updated_at=timezone.now())
		post_transaction.delay(txn.pk)
	for pending in Dispatch.objects.filter(status=Dispatch.PENDING, updated_at__lt=cutoff):
		send_dispatch.delay(pending.pk)
