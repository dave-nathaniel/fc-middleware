"""
Business rules for what the POS pushes to the middleware and what the Store
Requisition Portal (SRP) reads from and reports back to it.

Every receive_* function returns (ok, reason, extra) so the view can answer in
the Restroworks response format. Duplicate pushes are acknowledged without
creating anything new, so Restroworks can retry safely.
"""
import os
import logging
from collections import defaultdict
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone

from store_services.models import Store
from .models import PurchaseOrder, PurchaseOrderLink, Dispatch, InventoryTransaction, PosSale

logger = logging.getLogger(__name__)

BUSINESS_TZ = ZoneInfo(os.getenv("POS_BUSINESS_TIMEZONE", "Africa/Lagos"))


def internal_vendor_codes():
	"""POS vendor codes of the Warehouse, CK and PPU (comma separated in POS_INTERNAL_VENDOR_CODES)."""
	return {code.strip() for code in os.getenv("POS_INTERNAL_VENDOR_CODES", "").split(",") if code.strip()}


def business_date(moment=None):
	return (moment or timezone.now()).astimezone(BUSINESS_TZ).date()


def _store(store_id):
	return Store.objects.filter(pos_store_id=str(store_id)).first()


def _unknown_store(store_id):
	return False, f"Unknown storeId '{store_id}'. The outlet is not mapped to a store in the middleware.", {}


def _queue(txn):
	# Imported here so the models/services can be used without Celery configured (e.g. in the shell).
	# robust=True: if the broker is down the document is still accepted; the periodic
	# requeue task picks up anything left queued.
	from .tasks import post_transaction
	transaction.on_commit(lambda: post_transaction.delay(txn.pk), robust=True)


def _create_once(model, lookup, **fields):
	"""
		Creates the record, or returns None when an identical push created it first
		(two requests racing past the duplicate check). Other integrity errors propagate.
	"""
	try:
		with transaction.atomic():
			return model.objects.create(**lookup, **fields)
	except IntegrityError:
		if model.objects.filter(**lookup).exists():
			return None
		raise


# ----------------------------------------------------------------------------
# POS -> middleware
# ----------------------------------------------------------------------------
def receive_purchase_order(data, payload, clean):
	store = _store(data["storeId"])
	if not store:
		return _unknown_store(data["storeId"])

	items = [
		{"itemCode": item["itemCode"], "itemName": item.get("itemName", ""), "quantity": float(item["quantity"])}
		for item in data["items"]
	]
	codes = [item["itemCode"] for item in items]
	if len(codes) != len(set(codes)):
		return False, "The same itemCode appears more than once on the purchase order.", {}

	existing = PurchaseOrder.objects.filter(po_id=data["poId"]).first()
	if existing:
		return True, None, {"TotalCasesMessage": _total(existing.items)}

	vendor_code = str(data["vendor"]["code"])
	_create_once(
		PurchaseOrder, {"po_id": data["poId"]},
		prefix=data.get("prefix", ""),
		po_number=data["poNumber"],
		store=store,
		customer_key=data["customerKey"],
		vendor_code=vendor_code,
		vendor_name=data["vendor"].get("name", ""),
		supply_type=PurchaseOrder.SUPPLY_INTERNAL if vendor_code in internal_vendor_codes() else PurchaseOrder.SUPPLY_DIRECT,
		expected_delivery=data.get("expectedDelivery"),
		items=items,
		payload=payload,
		received_on=business_date(),
	)
	return True, None, {"TotalCasesMessage": _total(items)}


def _total(items):
	total = sum(float(item["quantity"]) for item in items)
	return int(total) if total.is_integer() else round(total, 4)


def _receive_transaction(kind, store, reference, clean, payload, **fields):
	with transaction.atomic():
		txn = _create_once(
			InventoryTransaction, {"kind": kind, "store": store, "reference": reference},
			data=clean, payload=payload, **fields,
		)
		if txn:
			_queue(txn)
	return True, None, {}


def receive_grn(data, payload, clean):
	store = _store(data["storeId"])
	if not store:
		return _unknown_store(data["storeId"])

	reference = str(data["transactionNumber"])
	if InventoryTransaction.objects.filter(kind=InventoryTransaction.GRN, store=store, reference=reference).exists():
		return True, None, {}

	dispatch = Dispatch.objects.filter(invoice_no=data["invoiceNo"], purchase_order__store=store).select_related("purchase_order").first()
	if not dispatch:
		return False, f"Unknown invoiceNo '{data['invoiceNo']}' for this store. GRNs must reference an invoice sent by the middleware.", {}

	dispatched_codes = {item["code"] for item in dispatch.payload["items"]}
	unknown = [item["itemCode"] for item in clean["items"] if item["itemCode"] not in dispatched_codes]
	if unknown:
		return False, f"Item(s) not on invoice {dispatch.invoice_no}: {', '.join(unknown)}.", {}

	return _receive_transaction(
		InventoryTransaction.GRN, store, reference, clean, payload,
		transaction_date=data["transactionDate"], dispatch=dispatch, purchase_order=dispatch.purchase_order,
	)


def receive_vendor_return(data, payload, clean):
	store = _store(data["storeId"])
	if not store:
		return _unknown_store(data["storeId"])

	reference = str(data["returnTransactionNo"])
	if InventoryTransaction.objects.filter(kind=InventoryTransaction.VENDOR_RETURN, store=store, reference=reference).exists():
		return True, None, {}

	po = PurchaseOrder.objects.filter(store=store, prefix=data.get("poPrefix", ""), po_number=data["poNumber"]).first()
	if not po:
		return False, f"Unknown purchase order {data.get('poPrefix', '')}{data['poNumber']} for this store.", {}

	received = InventoryTransaction.objects.filter(
		kind=InventoryTransaction.GRN, purchase_order=po, status=InventoryTransaction.POSTED
	)
	received_codes = {item["itemCode"] for txn in received for item in txn.data["items"]}
	unknown = [item["code"] for item in clean["items"] if item["code"] not in received_codes]
	if unknown:
		return False, f"Item(s) not yet received and posted against this purchase order: {', '.join(unknown)}.", {}

	return _receive_transaction(
		InventoryTransaction.VENDOR_RETURN, store, reference, clean, payload,
		transaction_date=data.get("returnDate") or timezone.now(), purchase_order=po,
	)


def receive_wastage(data, payload, clean):
	store = _store(data["storeId"])
	if not store:
		return _unknown_store(data["storeId"])

	reference = f"{data.get('wastagePrefix', '')}{data['wastageNumber']}"
	if InventoryTransaction.objects.filter(kind=InventoryTransaction.WASTAGE, store=store, reference=reference).exists():
		return True, None, {}

	return _receive_transaction(
		InventoryTransaction.WASTAGE, store, reference, clean, payload, transaction_date=data["wastageDate"],
	)


def receive_sales(data, payload, clean):
	"""
		Stores a store's sales for one business date. Each push carries the whole day,
		so a later push for the same store and date replaces the earlier one.
		Payment types are upper-cased, and repeated ones are added together.
	"""
	store = _store(data["storeId"])
	if not store:
		return _unknown_store(data["storeId"])

	totals = {}
	for tender in data["tenders"]:
		payment_type = " ".join(tender["paymentType"].split()).upper()
		totals[payment_type] = totals.get(payment_type, Decimal("0")) + tender["amount"]
	tenders = [{"paymentType": name, "amount": str(amount)} for name, amount in totals.items()]

	sale, created = PosSale.objects.update_or_create(
		store=store, business_date=data["businessDate"], defaults={"tenders": tenders, "payload": payload},
	)
	if not created:
		PosSale.objects.filter(pk=sale.pk).update(pushes=F("pushes") + 1)
		logger.info(f"Sales for {store.store_name} on {data['businessDate']} replaced by a new push.")
	return True, None, {}


# ----------------------------------------------------------------------------
# Blue Prism <-> middleware
# ----------------------------------------------------------------------------
def _icg_amount(value):
	"""ICG sends amounts as text with no trailing zeros: "528300", "1250.5"."""
	text = format(Decimal(value), "f")
	return text.rstrip("0").rstrip(".") if "." in text else text


def sales_for(date):
	"""
		POS sales for `date`, in the shape Blue Prism reads from ICG
		(GET /api/FoodConcept/Sales/{date}): one row per store and payment type,
		keyed by the store's ICG warehouse code. Zero amounts are left out, as ICG does.
	"""
	feed = []
	for sale in PosSale.objects.filter(business_date=date).select_related("store").order_by("store__icg_warehouse_code"):
		for tender in sale.tenders:
			if Decimal(tender["amount"]) == 0:
				continue
			feed.append({
				"warehouseCode": sale.store.icg_warehouse_code,
				"warehouseName": sale.store.icg_warehouse_name or sale.store.store_name,
				"date": date.isoformat(),
				"paymentType": tender["paymentType"],
				"amount": _icg_amount(tender["amount"]),
			})
	return feed


# ----------------------------------------------------------------------------
# SRP <-> middleware
# ----------------------------------------------------------------------------
def store_requests_for(date):
	"""
		Approved POS purchase orders received on `date`, in the shape the SRP
		already reads from ICG (GET /api/FoodConcept/StoreRequest/{date}), so the
		SRP only needs its base URL changed. Lines arrive pre-approved
		(is_declined=False) because approval happened in the POS.
	"""
	orders = PurchaseOrder.objects.filter(received_on=date).select_related("store").order_by("pk")
	feed = []
	for po in orders:
		feed.append({
			"series": po.prefix,
			"orderID": po.po_number,
			"supplierID": po.vendor_code,
			"itemLines": [
				{
					"lineId": index,
					"itemId": int(item["itemCode"]) if str(item["itemCode"]).isdigit() else 0,
					"reference": item["itemCode"],
					"description": item["itemName"] or item["itemCode"],
					"totalQuantity": item["quantity"],
					"unitPrice": 0,
					"totalPrice": 0,
					"warehouse": po.store.icg_warehouse_code,
					"is_declined": False,
					"remark": f"Approved in POS (Restroworks PO {po.prefix}{po.po_number}).",
				}
				for index, item in enumerate(po.items, start=1)
			],
		})
	return feed


def link_byd_document(data):
	"""
		Records which POS purchase orders went into a ByD document created by SRP.
		Returns (linked_po_numbers, unmatched_lines).
	"""
	grouped, unmatched = defaultdict(list), []
	for line in data["lines"]:
		po = PurchaseOrder.objects.filter(
			store__icg_warehouse_code=line["warehouse"], prefix=line["series"], po_number=line["orderID"]
		).first()
		if po is None:
			unmatched.append(line)
			continue
		grouped[po].append({"itemCode": line["reference"], "quantity": float(line["quantity"])})

	linked = []
	for po, lines in grouped.items():
		link, created = PurchaseOrderLink.objects.get_or_create(
			purchase_order=po,
			document_type=data["document_type"],
			document_id=str(data["document_id"]),
			defaults={"lines": lines},
		)
		if not created:
			link.lines = lines
			link.save(update_fields=["lines"])
		linked.append(f"{po.prefix}{po.po_number}")
	return linked, unmatched
