import os
import logging

from celery import shared_task

from .models import InventoryTransaction, Dispatch
from . import posting, dispatch as dispatching

logger = logging.getLogger(__name__)

MAX_RETRIES = int(os.getenv("POS_MAX_RETRIES", "6"))
# Seconds before retry n: 60, 120, 240 ... capped at 30 minutes.
BACKOFF_CAP = 1800


def _countdown(retries):
	return min(60 * (2 ** retries), BACKOFF_CAP)


@shared_task(bind=True, max_retries=MAX_RETRIES)
def post_transaction(self, txn_id):
	"""Posts a POS GRN, return or wastage to ByD, retrying with backoff on failure."""
	txn = InventoryTransaction.objects.select_related("store", "dispatch", "purchase_order").get(pk=txn_id)
	if txn.status == InventoryTransaction.POSTED:
		return
	txn.attempts += 1
	txn.save(update_fields=["attempts"])
	try:
		posting.post(txn)
	except posting.PostingError as e:
		# Our data is wrong; retrying won't fix it. Visible in the admin for correction.
		_mark_failed(txn, str(e))
	except Exception as e:
		_mark_failed(txn, str(e))
		raise self.retry(exc=e, countdown=_countdown(self.request.retries))


def _mark_failed(txn, error):
	logger.error(f"{txn}: {error}")
	txn.status = InventoryTransaction.FAILED
	txn.error = error[:4000]
	txn.save(update_fields=["status", "error"])


@shared_task(bind=True, max_retries=MAX_RETRIES)
def send_dispatch(self, dispatch_id):
	"""Sends one invoice to Restroworks."""
	dispatch = Dispatch.objects.select_related("purchase_order").get(pk=dispatch_id)
	if dispatch.status == Dispatch.SENT:
		return
	try:
		dispatching.send(dispatch)
	except Exception as e:
		logger.error(f"Invoice {dispatch.invoice_no}: {e}")
		raise self.retry(exc=e, countdown=_countdown(self.request.retries))


@shared_task
def sync_dispatches():
	"""Periodic: create invoices for ByD documents that are now due and send them."""
	for new_dispatch in dispatching.build_dispatches():
		send_dispatch.delay(new_dispatch.pk)
