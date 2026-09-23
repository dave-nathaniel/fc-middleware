"""
Returning ByD documents to the POS as invoices ("Dispatch / Invoice API").

A POS purchase order is linked (by the SRP, or manually in the admin) to the
ByD document demand planning created for it:

  sales_order      (Warehouse/CK/PPU)  one invoice per outbound delivery posted
                                       against the sales order, i.e. what was
                                       actually dispatched.
  purchase_order   (direct vendor)     one invoice once the ByD PO is issued, with
                                       the final ordered quantities and prices.
  purchase_request (direct vendor)     not dispatchable: ByD converts it to a PO,
                                       whose ID must then be linked (see README).

The store then records its GRN in the POS against that invoice number.
"""
import os
import logging
from collections import defaultdict

import requests
from django.db import transaction
from django.utils import timezone

from byd_services.rest import ByDClient
from .models import PurchaseOrderLink, Dispatch

logger = logging.getLogger(__name__)

# ByD PO lifecycle statuses that mean the order has been issued to the supplier.
PO_ISSUED_STATUSES = {"6", "9"}


# ----------------------------------------------------------------------------
# Building invoices from ByD documents
# ----------------------------------------------------------------------------
def _invoice_payload(po, invoice_no, invoice_date, lines):
	return {
		"storeId": po.store.pos_store_id,
		"prefix": po.prefix,
		"poNumber": po.po_number,
		"poId": po.po_id,
		"invoiceDate": invoice_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
		"invoiceNo": invoice_no,
		"items": [
			{
				"name": line["name"],
				"code": line["code"],
				"quantity": line["quantity"],
				"unitPrice": line["unit_price"],
				"subTotal": round(line["quantity"] * line["unit_price"], 2),
			}
			for line in lines
		],
	}


def _quantity(node):
	node = node or {}
	return float(node.get("Quantity") or 0), node.get("UnitCode") or node.get("unitCode") or ""


def dispatches_for_sales_order(so_id, client):
	"""Creates the invoices for outbound deliveries of one ByD sales order. Returns new Dispatches."""
	links = list(
		PurchaseOrderLink.objects.filter(document_type=PurchaseOrderLink.SALES_ORDER, document_id=so_id, open=True)
		.select_related("purchase_order__store").order_by("purchase_order__po_number")
	)
	if not links:
		return []

	created = []
	for delivery_ref in client.get_sales_order_outbound_deliveries(so_id):
		delivery_id = str(delivery_ref["ID"])
		if Dispatch.objects.filter(source_type=Dispatch.OUTBOUND_DELIVERY, source_id=delivery_id).exists():
			continue
		delivery = client.get_outbound_delivery(delivery_ref["ObjectID"])
		if not delivery:
			continue

		# Quantity shipped per item on this delivery.
		shipped, units, names = defaultdict(float), {}, {}
		for item in delivery["Item"]:
			quantity, unit = _quantity(item.get("ItemDeliveryQuantity"))
			shipped[item["ProductID"]] += quantity
			units[item["ProductID"]] = unit
			names[item["ProductID"]] = item.get("Description") or item["ProductID"]
		sender = (delivery.get("ShipFromLocation") or {}).get("LocationID") or ""

		# Several POS POs can share one sales order (SRP groups a store's requests per
		# supplier). Allocate what was shipped to them in PO order, up to what each
		# still has outstanding on this sales order.
		with transaction.atomic():
			for link in links:
				po = link.purchase_order
				lines = []
				for ordered in link.lines:
					code = ordered["itemCode"]
					outstanding = ordered["quantity"] - _already_dispatched(po, code)
					allocated = min(shipped.get(code, 0), max(outstanding, 0))
					if allocated <= 0:
						continue
					shipped[code] -= allocated
					lines.append({"code": code, "name": names.get(code, code), "quantity": allocated, "unit_price": 0})
				if not lines:
					continue
				invoice_no = f"{delivery_id}-{po.po_number}"
				invoice_date = timezone.now()
				created.append(Dispatch.objects.create(
					purchase_order=po,
					invoice_no=invoice_no,
					invoice_date=invoice_date,
					source_type=Dispatch.OUTBOUND_DELIVERY,
					source_id=delivery_id,
					byd_context={
						"sender_party_id": sender,
						"items": {line["code"]: {"unit_code": units.get(line["code"], "")} for line in lines},
					},
					payload=_invoice_payload(po, invoice_no, invoice_date, lines),
				))
			for link in links:
				if all(_already_dispatched(link.purchase_order, l["itemCode"]) >= l["quantity"] for l in link.lines):
					link.open = False
					link.save(update_fields=["open"])
	return created


def _already_dispatched(po, code):
	return sum(
		float(item["quantity"])
		for dispatch in po.dispatches.all()
		for item in dispatch.payload["items"]
		if item["code"] == code
	)


def dispatch_for_purchase_order(link, client):
	"""Creates the invoice for a ByD purchase order once it has been issued."""
	byd_po = client.get_purchase_order(link.document_id)
	if not byd_po or str(byd_po.get("LifeCycleStatusCode")) not in PO_ISSUED_STATUSES:
		return None

	po = link.purchase_order
	wanted = {item["itemCode"] for item in po.items}
	lines, items_context = [], {}
	for item in byd_po["Item"]:
		code = item.get("ProductID")
		if code not in wanted:
			continue
		quantity = float(item.get("Quantity") or 0)
		unit_price = float(item.get("ListUnitPriceAmount") or 0)
		lines.append({"code": code, "name": item.get("Description") or code, "quantity": quantity, "unit_price": unit_price})
		items_context[code] = {
			"unit_code": item.get("QuantityUnitCode", ""),
			"po_item_id": str(item.get("ID")),
			"po_item_type_code": str(item.get("ItemTypeCode")),
		}
	if not lines:
		logger.warning(f"ByD PO {link.document_id} has none of the items of POS PO {po}.")
		return None

	invoice_no = f"PO{link.document_id}-{po.po_number}"
	invoice_date = timezone.now()
	with transaction.atomic():
		dispatch = Dispatch.objects.create(
			purchase_order=po,
			invoice_no=invoice_no,
			invoice_date=invoice_date,
			source_type=Dispatch.PURCHASE_ORDER,
			source_id=str(link.document_id),
			byd_context={
				"sender_party_id": (byd_po.get("Supplier") or {}).get("PartyID", ""),
				"items": items_context,
			},
			payload=_invoice_payload(po, invoice_no, invoice_date, lines),
		)
		link.open = False
		link.save(update_fields=["open"])
	return dispatch


def build_dispatches(client=None):
	"""Checks every open link against ByD and creates the invoices that are now due."""
	client = client or ByDClient()
	created = []
	open_links = PurchaseOrderLink.objects.filter(open=True).select_related("purchase_order__store")
	for so_id in set(open_links.filter(document_type=PurchaseOrderLink.SALES_ORDER).values_list("document_id", flat=True)):
		try:
			created += dispatches_for_sales_order(so_id, client)
		except Exception as e:
			logger.error(f"Could not build dispatches for ByD sales order {so_id}: {e}")
	for link in open_links.filter(document_type=PurchaseOrderLink.PURCHASE_ORDER):
		try:
			dispatch = dispatch_for_purchase_order(link, client)
			if dispatch:
				created.append(dispatch)
		except Exception as e:
			logger.error(f"Could not build dispatch for ByD purchase order {link.document_id}: {e}")
	return created


# ----------------------------------------------------------------------------
# Sending invoices to Restroworks
# ----------------------------------------------------------------------------
def send(dispatch):
	"""Posts one invoice to Restroworks. Raises on failure."""
	response = requests.post(
		os.getenv("RESTROWORKS_INVOICE_URL"),
		params={"customer_key": dispatch.purchase_order.customer_key},
		headers={"Authorization": os.getenv("RESTROWORKS_AUTHORIZATION", "")},
		json=dispatch.payload,
		timeout=(15, 60),
	)
	try:
		body = response.json()
	except ValueError:
		body = {"raw": response.text[:2000]}

	dispatch.attempts += 1
	dispatch.response = body
	rejected = isinstance(body, dict) and str(body.get("Status", "")).lower() == "fail"
	if response.status_code >= 300 or rejected:
		dispatch.status = Dispatch.FAILED
		dispatch.save(update_fields=["attempts", "response", "status"])
		raise RuntimeError(f"Restroworks rejected invoice {dispatch.invoice_no} (HTTP {response.status_code}): {body}")

	dispatch.status = Dispatch.SENT
	dispatch.sent_at = timezone.now()
	dispatch.save(update_fields=["attempts", "response", "status", "sent_at"])
