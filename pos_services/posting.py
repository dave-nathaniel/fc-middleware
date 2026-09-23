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
	"""(item_code, signed quantity) for each line of the POS payload."""
	if txn.kind == InventoryTransaction.GRN:
		return [(item["itemCode"], float(item["quantity"])) for item in txn.payload["items"] if float(item["quantity"]) > 0]
	return [(item["code"], -float(item["quantity"])) for item in txn.payload["items"]]


def _context_dispatch(txn):
	"""The invoice whose ByD details (parties, units, PO item references) the posting uses."""
	if txn.dispatch_id:
		return txn.dispatch
	# Return to vendor: use the invoice of the latest GRN posted against the PO.
	grn = (
		InventoryTransaction.objects.filter(kind=InventoryTransaction.GRN, purchase_order=txn.purchase_order, status=InventoryTransaction.POSTED)
		.exclude(dispatch=None).order_by("-posted_at").first()
	)
	if not grn:
		raise PostingError("No posted GRN found for this purchase order.")
	return grn.dispatch


def build_inbound_delivery(txn):
	dispatch = _context_dispatch(txn)
	context = dispatch.byd_context
	doc_id = txn.byd_document_id
	items = []
	for index, (code, quantity) in enumerate(_lines(txn), start=1):
		item_context = context["items"].get(code)
		if not item_context:
			raise PostingError(f"Item {code} is not on ByD document {dispatch.source_id}.")
		item = {
			"ID": str(index),
			"TypeCode": "14",
			"ProductID": code,
			"ItemDeliveryQuantity": {"Quantity": str(quantity), "UnitCode": item_context["unit_code"]},
		}
		if dispatch.source_type == Dispatch.PURCHASE_ORDER:
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

	ship_to = COMPANY_ID if dispatch.source_type == Dispatch.PURCHASE_ORDER else txn.store.byd_cost_center_code
	return {
		"ID": doc_id,
		"ProcessingTypeCode": "SD",
		"Item": items,
		"SenderParty": {"PartyID": context["sender_party_id"]},
		"ShipToParty": {"PartyID": ship_to},
	}


def _post_inbound_delivery(txn, client):
	if not txn.byd_object_id:
		existing = client.find_inbound_delivery(txn.byd_document_id)
		if existing:
			if str(existing.get("ReleaseStatusCode")) == "3":
				logger.info(f"{txn.byd_document_id} already posted in ByD.")
				txn.byd_object_id = existing["ObjectID"]
				txn.save(update_fields=["byd_object_id"])
				return
			txn.byd_object_id = existing["ObjectID"]
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
		for index, item in enumerate(txn.payload["items"], start=1)
	]
	goods_movement.post_consumption_for_cost_center(
		external_id=txn.byd_document_id,
		cost_center_id=store.byd_cost_center_code,
		items=items,
		transaction_datetime=txn.transaction_date.isoformat(),
	)
