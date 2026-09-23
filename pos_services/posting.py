"""
Posting of POS inventory transactions into SAP ByD.

GRN            -> Inbound Delivery + Post Goods Receipt at the store.
                  Direct vendor: referenced to the ByD purchase order items
                  (same payload fc-vimp eGRN posts today).
                  Warehouse/CK/PPU: sent from the dispatching location to the
                  store (same payload as fc-vimp's warehouse-to-store receipt).
Vendor return  -> the same Inbound Delivery with negative quantities, which is
                  how fc-vimp reverses a GRN today.
Wastage        -> Goods consumption for the store's cost center.

Every ByD document gets an ID derived from our transaction ID, so a retried
task finds the document it already created instead of creating another one.
"""
import os
import logging
from time import sleep

import requests

from django.utils import timezone

from byd_services.rest import ByDClient
from byd_services import goods_movement
from .models import InventoryTransaction, Dispatch

logger = logging.getLogger(__name__)

COMPANY_ID = os.getenv("BYD_COMPANY_ID", "FC-0001")
ID_PREFIX = {InventoryTransaction.GRN: "RWG", InventoryTransaction.VENDOR_RETURN: "RWR", InventoryTransaction.WASTAGE: "RWW"}


class PostingError(Exception):
	"""A problem with our data (not ByD availability). Retrying will not help."""


def document_id(txn):
	return f"{ID_PREFIX[txn.kind]}{txn.pk}"


def post(txn, client=None):
	"""Posts one transaction. Raises on failure; the caller records the error and retries."""
	if txn.status == InventoryTransaction.POSTED:
		return
	txn.byd_document_id = txn.byd_document_id or document_id(txn)
	txn.save(update_fields=["byd_document_id"])

	if txn.kind == InventoryTransaction.WASTAGE:
		_post_wastage(txn)
	else:
		_post_inbound_delivery(txn, client or ByDClient())

	txn.status = InventoryTransaction.POSTED
	txn.error = ""
	txn.posted_at = timezone.now()
	txn.save(update_fields=["status", "error", "posted_at"])


# ----------------------------------------------------------------------------
# GRN and return to vendor
# ----------------------------------------------------------------------------
def _lines(txn):
	"""(item_code, signed quantity) for each line of the validated POS document."""
	if txn.kind == InventoryTransaction.GRN:
		return [(item["itemCode"], float(item["quantity"])) for item in txn.data["items"] if float(item["quantity"]) > 0]
	return [(item["code"], -float(item["quantity"])) for item in txn.data["items"]]


def _dispatch_for(txn, code):
	"""The invoice whose ByD details (parties, units, PO item references) this line posts with."""
	if txn.kind == InventoryTransaction.GRN:
		return txn.dispatch
	# Return to vendor: the invoice of the latest posted GRN of this PO that received the item.
	grns = (
		InventoryTransaction.objects.filter(kind=InventoryTransaction.GRN, purchase_order=txn.purchase_order, status=InventoryTransaction.POSTED)
		.exclude(dispatch=None).select_related("dispatch").order_by("-posted_at")
	)
	for grn in grns:
		if any(item["itemCode"] == code for item in grn.data["items"]):
			return grn.dispatch
	raise PostingError(f"No posted GRN of this purchase order received item {code}.")


def build_inbound_delivery(txn):
	doc_id = txn.byd_document_id
	items, senders, sources = [], set(), set()
	for index, (code, quantity) in enumerate(_lines(txn), start=1):
		dispatch = _dispatch_for(txn, code)
		context = dispatch.byd_context
		item_context = context["items"].get(code)
		if not item_context:
			raise PostingError(f"Item {code} is not on ByD document {dispatch.source_id}.")
		senders.add(context["sender_party_id"])
		sources.add(dispatch.source_type)
		item = {
			"ID": str(index),
			"TypeCode": "14",
			"ProductID": code,
			"ItemDeliveryQuantity": {"Quantity": str(quantity), "UnitCode": item_context["unit_code"]},
		}
		if dispatch.source_type == Dispatch.PURCHASE_ORDER:
			# Same shape fc-vimp eGRN posts: the item carries the PO item number.
			item["ID"] = item_context["po_item_id"]
			item["ItemPurchaseOrderReference"] = {
				"ID": dispatch.source_id,
				"ItemID": item_context["po_item_id"],
				"ItemTypeCode": item_context["po_item_type_code"],
				"RelationshipRoleCode": "1",
			}
			item["ItemSellerParty"] = {"PartyID": context["sender_party_id"]}
			item["ItemInboundDeliveryRequestReference"] = {
				"ID": doc_id, "ItemID": item_context["po_item_id"], "ItemTypeCode": "14", "TypeCode": "59", "RelationshipRoleCode": "1",
			}
		items.append(item)

	if not items:
		raise PostingError("Nothing to post: every line has a zero quantity.")
	if len(senders) > 1 or len(sources) > 1:
		raise PostingError("The lines come from different suppliers or supply types; post them as separate documents.")

	source_type = sources.pop()
	ship_to = COMPANY_ID if source_type == Dispatch.PURCHASE_ORDER else txn.store.byd_cost_center_code
	return {
		"ID": doc_id,
		"ProcessingTypeCode": "SD",
		"Item": items,
		"SenderParty": {"PartyID": senders.pop()},
		"ShipToParty": {"PartyID": ship_to},
	}


def _post_inbound_delivery(txn, client):
	# Always look the document up first: a previous attempt may have created it, or
	# even posted it and lost the response.
	existing = client.find_inbound_delivery(txn.byd_document_id)
	if existing:
		txn.byd_object_id = existing["ObjectID"]
		txn.save(update_fields=["byd_object_id"])
		if str(existing.get("ReleaseStatusCode")) == "3":
			logger.info(f"{txn.byd_document_id} is already posted in ByD.")
			return
	else:
		created = client.create_inbound_delivery(build_inbound_delivery(txn))
		txn.byd_object_id = created["ObjectID"]
		txn.save(update_fields=["byd_object_id"])
		# ByD needs a moment before the new delivery can be posted.
		sleep(int(os.getenv("BYD_POST_DELAY_SECONDS", "5")))
	client.post_goods_receipt(txn.byd_object_id)


# ----------------------------------------------------------------------------
# Wastage
# ----------------------------------------------------------------------------
def _post_wastage(txn):
	store = txn.store
	items = [
		{"line": index, "product_id": item["itemCode"], "quantity": float(item["quantity"]), "unit_code": item["unitCode"]}
		for index, item in enumerate(txn.data["items"], start=1)
	]
	try:
		goods_movement.post_consumption_for_cost_center(
			external_id=txn.byd_document_id,
			cost_center_id=store.byd_cost_center_code,
			items=items,
			transaction_datetime=txn.transaction_date.isoformat(),
		)
	except requests.exceptions.ReadTimeout:
		# ByD may have posted it: the consumption service cannot be queried by our ID,
		# so resending automatically could post the wastage twice.
		raise PostingError(
			f"ByD did not answer in time. Check ByD for goods movement external ID {txn.byd_document_id} "
			f"before using 'Retry posting'."
		)
