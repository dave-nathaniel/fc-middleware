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


def _ordered(link, po):
	"""Quantity per item that went into the linked ByD document (the POS PO when entered manually)."""
	lines = link.lines or [{"itemCode": item["itemCode"], "quantity": item["quantity"]} for item in po.items]
	return [(line["itemCode"], float(line["quantity"])) for line in lines]


def _already_dispatched(po, code):
	return sum(
		float(item["quantity"])
		for dispatch in po.dispatches.all()
		for item in dispatch.payload["items"]
		if item["code"] == code
	)


def _allocate(links, available, describe):
	"""
		Splits what a ByD document holds across the POS POs linked to it, in PO order,
		up to what each still has outstanding. `available` is {item_code: quantity}
		and is reduced in place. Returns [(link, [line, ...])].
	"""
	allocations = []
	for link in links:
		po = link.purchase_order
		lines = []
		for code, ordered in _ordered(link, po):
			outstanding = ordered - _already_dispatched(po, code)
			allocated = min(available.get(code, 0), max(outstanding, 0))
			if allocated <= 0:
				continue
			available[code] -= allocated
			lines.append({"code": code, **describe(code), "quantity": allocated})
		if lines:
			allocations.append((link, lines))
	return allocations


def _close_fulfilled(links):
	for link in links:
		po = link.purchase_order
		if all(_already_dispatched(po, code) >= quantity for code, quantity in _ordered(link, po)):
			link.open = False
			link.save(update_fields=["open"])


def _open_links(document_type, document_id):
	return list(
		PurchaseOrderLink.objects.filter(document_type=document_type, document_id=document_id, open=True)
		.select_related("purchase_order__store").order_by("purchase_order__po_number", "purchase_order__pk")
	)


def _shipped(delivery):
	"""False for deliveries that are cancelled or not yet released (goods not issued)."""
	if str(delivery.get("CancellationStatusCode", "")) == "4":
		return False
	release = delivery.get("ReleaseStatusCode")
	return release is None or str(release) == "3"


def dispatches_for_sales_order(so_id, client):
	"""Creates the invoices for outbound deliveries of one ByD sales order. Returns new Dispatches."""
	links = _open_links(PurchaseOrderLink.SALES_ORDER, so_id)
	if not links:
		return []

	created = []
	for delivery_ref in client.get_sales_order_outbound_deliveries(so_id):
		delivery_id = str(delivery_ref["ID"])
		if Dispatch.objects.filter(source_type=Dispatch.OUTBOUND_DELIVERY, source_id=delivery_id).exists():
			continue
		delivery = client.get_outbound_delivery(delivery_ref["ObjectID"])
		if not delivery or not _shipped(delivery):
			continue

		available, units, names = defaultdict(float), {}, {}
		for item in delivery["Item"]:
			quantity, unit = _quantity(item.get("ItemDeliveryQuantity"))
			available[item["ProductID"]] += quantity
			units[item["ProductID"]] = unit
			names[item["ProductID"]] = item.get("Description") or item["ProductID"]
		sender = (delivery.get("ShipFromLocation") or {}).get("LocationID") or ""
		describe = lambda code: {"name": names.get(code, code), "unit_price": 0}

		with transaction.atomic():
			for link, lines in _allocate(links, available, describe):
				po = link.purchase_order
				created.append(_create_dispatch(
					po, f"{delivery_id}-{po.store.pos_store_id}-{po.po_number}", Dispatch.OUTBOUND_DELIVERY, delivery_id,
					{"sender_party_id": sender, "items": {line["code"]: {"unit_code": units.get(line["code"], "")} for line in lines}},
					lines,
				))
			_close_fulfilled(links)
	return created


def dispatches_for_purchase_order(byd_po_id, client):
	"""Creates the invoices for a ByD purchase order once it has been issued, split across its POS POs."""
	links = _open_links(PurchaseOrderLink.PURCHASE_ORDER, byd_po_id)
	if not links:
		return []
	byd_po = client.get_purchase_order(byd_po_id)
	if not byd_po or str(byd_po.get("LifeCycleStatusCode")) not in PO_ISSUED_STATUSES:
		return []

	available, details = defaultdict(float), {}
	for item in byd_po["Item"]:
		code = item.get("ProductID")
		if not code or str(item.get("CancellationStatusCode", "")) == "4":
			continue
		available[code] += float(item.get("Quantity") or 0)
		details[code] = {
			"name": item.get("Description") or code,
			"unit_price": float(item.get("ListUnitPriceAmount") or 0),
			"context": {
				"unit_code": item.get("QuantityUnitCode", ""),
				"po_item_id": str(item.get("ID")),
				"po_item_type_code": str(item.get("ItemTypeCode")),
			},
		}
	describe = lambda code: {"name": details[code]["name"], "unit_price": details[code]["unit_price"]}
	sender = (byd_po.get("Supplier") or {}).get("PartyID", "")

	created = []
	with transaction.atomic():
		for link, lines in _allocate(links, available, describe):
			po = link.purchase_order
			created.append(_create_dispatch(
				po, f"PO{byd_po_id}-{po.store.pos_store_id}-{po.po_number}", Dispatch.PURCHASE_ORDER, str(byd_po_id),
				{"sender_party_id": sender, "items": {line["code"]: details[line["code"]]["context"] for line in lines}},
				lines,
			))
		# One issued ByD PO is invoiced once; later changes need a new POS PO (Restroworks cannot amend).
		for link in links:
			link.open = False
			link.save(update_fields=["open"])
	if not created:
		logger.warning(f"ByD PO {byd_po_id} has none of the items of its linked POS purchase orders.")
	return created


def _create_dispatch(po, invoice_no, source_type, source_id, byd_context, lines):
	invoice_date = timezone.now()
	return Dispatch.objects.create(
		purchase_order=po,
		invoice_no=invoice_no,
		invoice_date=invoice_date,
		source_type=source_type,
		source_id=source_id,
		byd_context=byd_context,
		payload=_invoice_payload(po, invoice_no, invoice_date, lines),
	)


def build_dispatches(client=None):
	"""Checks every open link against ByD and creates the invoices that are now due."""
	client = client or ByDClient()
	created = []
	open_links = PurchaseOrderLink.objects.filter(open=True)
	builders = {
		PurchaseOrderLink.SALES_ORDER: dispatches_for_sales_order,
		PurchaseOrderLink.PURCHASE_ORDER: dispatches_for_purchase_order,
	}
	for document_type, build in builders.items():
		for document_id in set(open_links.filter(document_type=document_type).values_list("document_id", flat=True)):
			try:
				created += build(document_id, client)
			except Exception as e:
				logger.error(f"Could not build invoices for ByD {document_type} {document_id}: {e}")
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
