"""
Tests for the Restroworks POS integration. ByD and Restroworks are mocked.

Run with (CELERY_TASK_ALWAYS_EAGER makes queued tasks run inline):
	CELERY_TASK_ALWAYS_EAGER=True BYD_POST_DELAY_SECONDS=0 python manage.py test pos_services
"""
import os
from unittest import mock

from datetime import timedelta

import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from store_services.models import Store
from .models import PurchaseOrder, PurchaseOrderLink, Dispatch, InventoryTransaction, PosSale
from . import dispatch as dispatching

User = get_user_model()

PO_PAYLOAD = {
	"storeId": "3727",
	"customerKey": "630b9e49e5513ae61ffd43ec",
	"expectedDelivery": "2026-09-30T08:30:00.000Z",
	"prefix": "BP/O1-19-20/",
	"poNumber": 158,
	"poId": "5968917d3a46db083bc22bff",
	"updated": "2026-09-28T16:56:41.944Z",
	"created": "2026-09-28T16:56:05.133Z",
	"store": {"name": "MAIN STORE", "storeUID": "SA1", "type": "store"},
	"vendor": {"name": "DEMO VENDOR 1", "code": "1011"},
	"items": [
		{"itemName": "OIL CORN 4*3.5ltr (Pcs)", "itemCode": "10047", "quantity": 10},
		{"itemName": "Tomato Ketchup", "itemCode": "10048", "quantity": 10},
	],
}


class FakeByD:
	"""Stands in for byd_services.rest.ByDClient."""

	def __init__(self, existing_delivery=None):
		self.created = []
		self.posted = []
		self.existing_delivery = existing_delivery

	def find_inbound_delivery(self, external_id):
		return self.existing_delivery

	def create_inbound_delivery(self, payload):
		self.created.append(payload)
		return {"ObjectID": f"OBJ-{payload['ID']}"}

	def post_goods_receipt(self, object_id):
		self.posted.append(object_id)
		return {}

	def get_sales_order_outbound_deliveries(self, so_id):
		return [{"ID": "81", "ObjectID": "OD81"}]

	def get_outbound_delivery(self, object_id):
		return {
			"ID": "81",
			"ShipFromLocation": {"LocationID": "13101"},
			"Item": [
				{"ProductID": "10047", "Description": "Corn oil", "ItemDeliveryQuantity": {"Quantity": "15", "UnitCode": "EA"}},
				{"ProductID": "10048", "Description": "Ketchup", "ItemDeliveryQuantity": {"Quantity": "10", "UnitCode": "EA"}},
			],
		}

	def get_purchase_order(self, po_id):
		return {
			"ID": po_id,
			"LifeCycleStatusCode": "6",
			"Supplier": {"PartyID": "V1011"},
			"Item": [
				{"ID": "10", "ItemTypeCode": "18", "ProductID": "10047", "Description": "Corn oil", "Quantity": "8",
				 "QuantityUnitCode": "EA", "ListUnitPriceAmount": "25000"},
				{"ID": "20", "ItemTypeCode": "18", "ProductID": "10048", "Description": "Ketchup", "Quantity": "10",
				 "QuantityUnitCode": "EA", "ListUnitPriceAmount": "3000"},
			],
		}


@mock.patch.dict(os.environ, {"POS_INTERNAL_VENDOR_CODES": "178,179,180", "BYD_POST_DELAY_SECONDS": "0"})
class PosIntegrationTests(TestCase):

	def setUp(self):
		self.user = User.objects.create_user(username="restroworks", password="secret")
		self.user.groups.add(Group.objects.create(name="restroworks"))
		self.srp_user = User.objects.create_user(username="srp", password="srp-secret")
		self.srp_user.groups.add(Group.objects.create(name="store_requisition"))
		self.client = APIClient()
		self.client.credentials(HTTP_AUTHORIZATION="Basic cmVzdHJvd29ya3M6c2VjcmV0")  # restroworks:secret
		self.srp = APIClient()
		self.srp.force_authenticate(self.srp_user)
		self.store = Store.objects.create(
			store_name="CR Adeniran", icg_warehouse_name="ADENIRAN", icg_warehouse_code="W101",
			byd_cost_center_code="4100003-17", pos_store_id="3727",
		)

	# ------------------------------------------------------------------
	# helpers
	# ------------------------------------------------------------------
	def push(self, path, payload):
		response = self.client.post(f"/api/v1/pos/{path}", payload, format="json")
		self.assertEqual(response.status_code, 200)
		return response.json()

	def push_po(self, **overrides):
		return self.push("purchase-orders", {**PO_PAYLOAD, **overrides})

	def linked_po(self, document_type, document_id, **overrides):
		self.push_po(**overrides)
		po = PurchaseOrder.objects.get(po_id=overrides.get("poId", PO_PAYLOAD["poId"]))
		PurchaseOrderLink.objects.create(
			purchase_order=po, document_type=document_type, document_id=document_id,
			lines=[{"itemCode": i["itemCode"], "quantity": i["quantity"]} for i in po.items],
		)
		return po

	def grn_payload(self, invoice_no, transaction_number=183, quantity=8):
		return {
			"customerKey": PO_PAYLOAD["customerKey"],
			"invoiceDate": "2026-09-29T18:30:00.000Z",
			"invoiceNo": invoice_no,
			"transactionNumber": transaction_number,
			"storeId": "3727",
			"transactionDate": "2026-09-30T17:20:16.098Z",
			"items": [{"quantity": quantity, "itemCode": "10047", "itemName": "OIL CORN"}],
		}

	# ------------------------------------------------------------------
	# Purchase orders
	# ------------------------------------------------------------------
	def test_requires_authentication(self):
		response = APIClient().post("/api/v1/pos/purchase-orders", PO_PAYLOAD, format="json")
		self.assertEqual(response.status_code, 401)

	def test_purchase_order_is_stored_once(self):
		self.assertEqual(self.push_po(), {"Status": "Success", "TotalCasesMessage": 20})
		self.assertEqual(self.push_po(), {"Status": "Success", "TotalCasesMessage": 20})
		po = PurchaseOrder.objects.get()
		self.assertEqual(po.supply_type, PurchaseOrder.SUPPLY_DIRECT)
		self.assertEqual(po.store, self.store)

	def test_internal_vendor_is_classified(self):
		self.push_po(vendor={"name": "WAREHOUSE", "code": "178"})
		self.assertEqual(PurchaseOrder.objects.get().supply_type, PurchaseOrder.SUPPLY_INTERNAL)

	def test_unknown_store_and_bad_payload_fail_with_reason(self):
		body = self.push_po(storeId="9999")
		self.assertEqual(body["Status"], "Fail")
		self.assertIn("Unknown storeId", body["Reason"])
		body = self.push_po(items=[])
		self.assertEqual(body["Status"], "Fail")
		self.assertIn("items", body["Reason"])

	# ------------------------------------------------------------------
	# SRP feed and link-back
	# ------------------------------------------------------------------
	def test_srp_feed_matches_icg_shape(self):
		self.push_po()
		po = PurchaseOrder.objects.get()
		token = self.client.post("/srp-feed/token", {"grant_type": "password", "username": "srp", "password": "srp-secret"})
		self.assertEqual(token.status_code, 200)
		feed_client = APIClient()
		feed_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.json()['access_token']}")
		feed = feed_client.get(f"/srp-feed/api/FoodConcept/StoreRequest/{po.received_on.isoformat()}").json()
		self.assertEqual(len(feed), 1)
		self.assertEqual(feed[0]["series"], "BP/O1-19-20/")
		self.assertEqual(feed[0]["orderID"], 158)
		self.assertEqual(feed[0]["supplierID"], "1011")
		line = feed[0]["itemLines"][0]
		self.assertEqual(line["reference"], "10047")
		self.assertEqual(line["warehouse"], "W101")
		self.assertFalse(line["is_declined"])

	def test_feed_token_is_limited_to_srp_and_to_the_feed(self):
		# Wrong password, and a valid user outside the SRP group, both get no token.
		self.assertEqual(self.client.post("/srp-feed/token", {"grant_type": "password", "username": "srp", "password": "nope"}).status_code, 400)
		self.assertEqual(self.client.post("/srp-feed/token", {"grant_type": "password", "username": "restroworks", "password": "secret"}).status_code, 400)
		token = self.client.post("/srp-feed/token", {"grant_type": "password", "username": "srp", "password": "srp-secret"}).json()["access_token"]
		other = APIClient()
		other.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
		self.assertEqual(other.get("/api/v1/stores").status_code, 401)

	def test_endpoints_are_limited_to_their_caller(self):
		# Restroworks cannot link documents; SRP cannot push POS documents.
		response = self.client.post("/api/v1/pos/purchase-orders/link", {}, format="json")
		self.assertEqual(response.status_code, 403)
		self.assertEqual(self.srp.post("/api/v1/pos/purchase-orders", PO_PAYLOAD, format="json").status_code, 403)

	def test_link_from_srp(self):
		self.push_po()
		response = self.srp.post("/api/v1/pos/purchase-orders/link", {
			"document_type": "sales_order", "document_id": "5001",
			"lines": [
				{"warehouse": "W101", "series": "BP/O1-19-20/", "orderID": 158, "reference": "10047", "quantity": 10},
				{"warehouse": "W101", "series": "BP/O1-19-20/", "orderID": 999, "reference": "10047", "quantity": 1},
			],
		}, format="json")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["data"]["linked"], ["BP/O1-19-20/158"])
		self.assertEqual(len(response.json()["data"]["unmatched"]), 1)
		link = PurchaseOrderLink.objects.get()
		self.assertEqual(link.lines, [{"itemCode": "10047", "quantity": 10.0}])

	# ------------------------------------------------------------------
	# Dispatch / invoice back to the POS
	# ------------------------------------------------------------------
	def test_outbound_delivery_is_split_across_pos_on_one_sales_order(self):
		first = self.linked_po("sales_order", "5001", vendor={"code": "178"})
		second = self.linked_po("sales_order", "5001", vendor={"code": "178"}, poId="second", poNumber=159)
		created = dispatching.build_dispatches(client=FakeByD())
		self.assertEqual(len(created), 2)
		first_invoice = Dispatch.objects.get(purchase_order=first)
		second_invoice = Dispatch.objects.get(purchase_order=second)
		self.assertEqual(first_invoice.invoice_no, "81-3727-158")
		self.assertEqual({i["code"]: i["quantity"] for i in first_invoice.payload["items"]}, {"10047": 10, "10048": 10})
		# 15 corn oil shipped: 10 to the first PO, 5 left for the second; no ketchup left.
		self.assertEqual({i["code"]: i["quantity"] for i in second_invoice.payload["items"]}, {"10047": 5})
		self.assertEqual(first_invoice.byd_context["sender_party_id"], "13101")
		self.assertFalse(PurchaseOrderLink.objects.get(purchase_order=first).open)
		self.assertTrue(PurchaseOrderLink.objects.get(purchase_order=second).open)
		# Running again does not invoice the same delivery twice.
		self.assertEqual(dispatching.build_dispatches(client=FakeByD()), [])

	def test_issued_purchase_order_becomes_invoice_with_final_quantities(self):
		po = self.linked_po("purchase_order", "7001")
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		self.assertEqual(invoice.invoice_no, "PO7001-3727-158")
		self.assertEqual(invoice.payload["poId"], po.po_id)
		corn = next(i for i in invoice.payload["items"] if i["code"] == "10047")
		self.assertEqual((corn["quantity"], corn["unitPrice"], corn["subTotal"]), (8.0, 25000.0, 200000.0))
		self.assertEqual(invoice.byd_context["items"]["10047"]["po_item_id"], "10")

	@mock.patch("pos_services.dispatch.requests.post")
	def test_send_invoice_to_restroworks(self, post):
		self.linked_po("purchase_order", "7001")
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		post.return_value = mock.Mock(status_code=200, json=lambda: {"Status": "Success"})
		dispatching.send(invoice)
		invoice.refresh_from_db()
		self.assertEqual(invoice.status, Dispatch.SENT)
		self.assertEqual(post.call_args.kwargs["params"], {"customer_key": PO_PAYLOAD["customerKey"]})

		post.return_value = mock.Mock(status_code=200, json=lambda: {"Status": "Fail", "Reason": "bad"})
		invoice.status = Dispatch.PENDING
		with self.assertRaises(RuntimeError):
			dispatching.send(invoice)
		self.assertEqual(invoice.status, Dispatch.FAILED)

	# ------------------------------------------------------------------
	# GRN, return to vendor, wastage
	# ------------------------------------------------------------------
	def test_grn_against_purchase_order_invoice_posts_inbound_delivery(self):
		self.linked_po("purchase_order", "7001")
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		byd = FakeByD()
		with mock.patch("pos_services.posting.ByDClient", return_value=byd), self.captureOnCommitCallbacks(execute=True):
			body = self.push("grns", self.grn_payload(invoice.invoice_no))
		self.assertEqual(body, {"Status": "Success"})
		txn = InventoryTransaction.objects.get(kind=InventoryTransaction.GRN)
		self.assertEqual(txn.status, InventoryTransaction.POSTED)
		[payload] = byd.created
		self.assertEqual(payload["ID"], f"RWG{txn.pk}")
		self.assertEqual(payload["SenderParty"], {"PartyID": "V1011"})
		item = payload["Item"][0]
		self.assertEqual(item["ItemPurchaseOrderReference"]["ID"], "7001")
		self.assertEqual(item["ItemPurchaseOrderReference"]["ItemID"], "10")
		self.assertEqual(item["ItemDeliveryQuantity"], {"Quantity": "8.0", "UnitCode": "EA"})
		self.assertEqual(byd.posted, [f"OBJ-RWG{txn.pk}"])

		# A duplicate push is acknowledged and not posted again.
		with mock.patch("pos_services.posting.ByDClient", return_value=byd), self.captureOnCommitCallbacks(execute=True):
			self.assertEqual(self.push("grns", self.grn_payload(invoice.invoice_no)), {"Status": "Success"})
		self.assertEqual(len(byd.created), 1)

	def test_grn_against_outbound_delivery_ships_to_store(self):
		self.linked_po("sales_order", "5001", vendor={"code": "178"})
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		byd = FakeByD()
		with mock.patch("pos_services.posting.ByDClient", return_value=byd), self.captureOnCommitCallbacks(execute=True):
			self.push("grns", self.grn_payload(invoice.invoice_no, quantity=10))
		[payload] = byd.created
		self.assertEqual(payload["SenderParty"], {"PartyID": "13101"})
		self.assertEqual(payload["ShipToParty"], {"PartyID": "4100003-17"})
		self.assertNotIn("ItemPurchaseOrderReference", payload["Item"][0])

	def test_grn_retry_resumes_existing_byd_document(self):
		self.linked_po("purchase_order", "7001")
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		byd = FakeByD(existing_delivery={"ObjectID": "EXISTING", "ReleaseStatusCode": "1"})
		with mock.patch("pos_services.posting.ByDClient", return_value=byd), self.captureOnCommitCallbacks(execute=True):
			self.push("grns", self.grn_payload(invoice.invoice_no))
		self.assertEqual(byd.created, [])
		self.assertEqual(byd.posted, ["EXISTING"])

	def test_grn_with_unknown_invoice_or_item_fails(self):
		body = self.push("grns", self.grn_payload("NOPE"))
		self.assertEqual(body["Status"], "Fail")
		self.linked_po("purchase_order", "7001")
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		payload = self.grn_payload(invoice.invoice_no)
		payload["items"][0]["itemCode"] = "99999"
		body = self.push("grns", payload)
		self.assertEqual(body["Status"], "Fail")
		self.assertIn("99999", body["Reason"])

	def test_vendor_return_reverses_with_negative_quantities(self):
		self.linked_po("purchase_order", "7001")
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		byd = FakeByD()
		return_payload = {
			"storeId": "3727", "poPrefix": "BP/O1-19-20/", "poNumber": "158", "returnPrefix": "RE",
			"returnTransactionNo": 23, "items": [{"name": "OIL CORN", "code": "10047", "quantity": 2}],
		}
		# Nothing received yet: the return is refused.
		self.assertEqual(self.push("vendor-returns", return_payload)["Status"], "Fail")

		with mock.patch("pos_services.posting.ByDClient", return_value=byd):
			with self.captureOnCommitCallbacks(execute=True):
				self.push("grns", self.grn_payload(invoice.invoice_no))
			with self.captureOnCommitCallbacks(execute=True):
				body = self.push("vendor-returns", return_payload)
		self.assertEqual(body, {"Status": "Success"})
		reversal = byd.created[1]
		self.assertTrue(reversal["ID"].startswith("RWR"))
		self.assertEqual(reversal["Item"][0]["ItemDeliveryQuantity"]["Quantity"], "-2.0")
		self.assertEqual(InventoryTransaction.objects.get(kind=InventoryTransaction.VENDOR_RETURN).status, InventoryTransaction.POSTED)

	@mock.patch("pos_services.posting.goods_movement.post_consumption_for_cost_center")
	def test_wastage_posts_goods_consumption(self, consume):
		payload = {
			"storeId": "3727", "wastagePrefix": "WS", "wastageNumber": "41", "wastageDate": "2026-09-30T05:00:00Z",
			"recordedBy": "store.manager@foodconceptsplc.com",
			"items": [{"itemCode": "RM1000072", "quantity": 1.5, "unitCode": "KGM", "reasonCode": "EXP", "reasonDescription": "Expired"}],
		}
		with self.captureOnCommitCallbacks(execute=True):
			self.assertEqual(self.push("wastage", payload), {"Status": "Success"})
		txn = InventoryTransaction.objects.get(kind=InventoryTransaction.WASTAGE)
		self.assertEqual(txn.status, InventoryTransaction.POSTED)
		kwargs = consume.call_args.kwargs
		self.assertEqual(kwargs["cost_center_id"], "4100003-17")
		self.assertEqual(kwargs["external_id"], f"RWW{txn.pk}")
		self.assertEqual(kwargs["items"][0]["unit_code"], "KGM")

		del payload["items"][0]["reasonCode"]
		payload["wastageNumber"] = "42"
		self.assertIn("reasonCode", self.push("wastage", payload)["Reason"])

	def test_byd_failure_keeps_record_queued_for_retry(self):
		self.linked_po("purchase_order", "7001")
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		byd = FakeByD()
		byd.post_goods_receipt = mock.Mock(side_effect=Exception("Object is locked"))
		with mock.patch("pos_services.posting.ByDClient", return_value=byd), \
				mock.patch("pos_services.tasks.post_transaction.retry", side_effect=RuntimeError("retry scheduled")), \
				self.captureOnCommitCallbacks(execute=False) as callbacks:
			self.push("grns", self.grn_payload(invoice.invoice_no))
		with mock.patch("pos_services.posting.ByDClient", return_value=byd), \
				mock.patch("pos_services.tasks.post_transaction.retry", side_effect=RuntimeError("retry scheduled")):
			for callback in callbacks:
				try:
					callback()
				except RuntimeError:
					pass
		txn = InventoryTransaction.objects.get(kind=InventoryTransaction.GRN)
		self.assertEqual(txn.status, InventoryTransaction.QUEUED)
		self.assertIn("locked", txn.error)
		self.assertEqual(txn.attempts, 1)

	def test_grn_already_posted_in_byd_is_not_posted_again(self):
		self.linked_po("purchase_order", "7001")
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		byd = FakeByD(existing_delivery={"ObjectID": "DONE", "ReleaseStatusCode": "3"})
		with mock.patch("pos_services.posting.ByDClient", return_value=byd), self.captureOnCommitCallbacks(execute=True):
			self.push("grns", self.grn_payload(invoice.invoice_no))
		self.assertEqual((byd.created, byd.posted), ([], []))
		self.assertEqual(InventoryTransaction.objects.get().status, InventoryTransaction.POSTED)

	def test_numeric_item_codes_are_treated_as_text(self):
		self.linked_po("purchase_order", "7001")
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		payload = self.grn_payload(invoice.invoice_no)
		payload["items"][0]["itemCode"] = 10047
		byd = FakeByD()
		with mock.patch("pos_services.posting.ByDClient", return_value=byd), self.captureOnCommitCallbacks(execute=True):
			self.assertEqual(self.push("grns", payload), {"Status": "Success"})
		self.assertEqual(InventoryTransaction.objects.get().status, InventoryTransaction.POSTED)
		self.assertEqual(byd.created[0]["Item"][0]["ProductID"], "10047")

	def test_one_byd_po_for_several_stores_is_split(self):
		other = Store.objects.create(
			store_name="CR Allen", icg_warehouse_name="ALLEN", icg_warehouse_code="W202",
			byd_cost_center_code="4100003-18", pos_store_id="4000",
		)
		first = self.linked_po("purchase_order", "7001")
		second = self.linked_po("purchase_order", "7001", storeId="4000", poId="other-store")
		for po in (first, second):
			link = po.links.get()
			link.lines = [{"itemCode": "10047", "quantity": 4}]
			link.save()
		invoices = dispatching.build_dispatches(client=FakeByD())
		self.assertEqual(sorted(i.invoice_no for i in invoices), ["PO7001-3727-158", "PO7001-4000-158"])
		for invoice in invoices:
			self.assertEqual([(i["code"], i["quantity"]) for i in invoice.payload["items"]], [("10047", 4.0)])
		self.assertEqual(second.store, other)

	def test_unreleased_or_cancelled_delivery_is_not_invoiced(self):
		self.linked_po("sales_order", "5001", vendor={"code": "178"})
		byd = FakeByD()
		original = byd.get_outbound_delivery
		byd.get_outbound_delivery = lambda object_id: {**original(object_id), "ReleaseStatusCode": "1"}
		self.assertEqual(dispatching.build_dispatches(client=byd), [])
		byd.get_outbound_delivery = lambda object_id: {**original(object_id), "CancellationStatusCode": "4"}
		self.assertEqual(dispatching.build_dispatches(client=byd), [])

	@mock.patch("pos_services.posting.goods_movement.post_consumption_for_cost_center", side_effect=requests.exceptions.ReadTimeout())
	def test_wastage_with_unknown_outcome_waits_for_a_person(self, consume):
		payload = {
			"storeId": "3727", "wastageNumber": "43", "wastageDate": "2026-09-30T05:00:00Z", "recordedBy": "sm",
			"items": [{"itemCode": "RM1", "quantity": 1, "unitCode": "KGM", "reasonCode": "EXP"}],
		}
		with self.captureOnCommitCallbacks(execute=True):
			self.push("wastage", payload)
		txn = InventoryTransaction.objects.get()
		self.assertEqual(txn.status, InventoryTransaction.FAILED)
		self.assertIn("Check ByD", txn.error)
		self.assertEqual(consume.call_count, 1)

	def test_stale_records_are_requeued(self):
		from .tasks import requeue_stale
		self.linked_po("purchase_order", "7001")
		[invoice] = dispatching.build_dispatches(client=FakeByD())
		# The broker was down when the GRN arrived: it was stored but never queued.
		with mock.patch("pos_services.tasks.post_transaction.delay", side_effect=ConnectionError("redis down")), \
				self.captureOnCommitCallbacks(execute=True):
			self.assertEqual(self.push("grns", self.grn_payload(invoice.invoice_no)), {"Status": "Success"})
		txn = InventoryTransaction.objects.get()
		self.assertEqual(txn.status, InventoryTransaction.QUEUED)
		InventoryTransaction.objects.filter(pk=txn.pk).update(updated_at=timezone.now() - timedelta(hours=1))
		Dispatch.objects.filter(pk=invoice.pk).update(updated_at=timezone.now() - timedelta(hours=1))
		byd = FakeByD()
		with mock.patch("pos_services.posting.ByDClient", return_value=byd), \
				mock.patch("pos_services.dispatch.requests.post", return_value=mock.Mock(status_code=200, json=lambda: {"Status": "Success"})):
			requeue_stale()
		txn.refresh_from_db()
		invoice.refresh_from_db()
		self.assertEqual(txn.status, InventoryTransaction.POSTED)
		self.assertEqual(invoice.status, Dispatch.SENT)


SALES_PAYLOAD = {
	"storeId": "3727",
	"businessDate": "2026-10-22",
	"tenders": [
		{"paymentType": "CASH", "amount": 528300},
		{"paymentType": "Debit Card", "amount": "541700.50"},
		{"paymentType": "BANK TRANSFER", "amount": 148700},
		{"paymentType": "BANK  TRANSFER", "amount": 1000},
		{"paymentType": "CREDIT", "amount": 0},
	],
}


class SalesTests(TestCase):
	"""POS sales pushed by Restroworks and served to Blue Prism in ICG's format."""

	def setUp(self):
		restroworks = User.objects.create_user(username="restroworks", password="secret")
		restroworks.groups.add(Group.objects.create(name="restroworks"))
		blue_prism = User.objects.create_user(username="bp", password="bp-secret")
		blue_prism.groups.add(Group.objects.create(name="blue_prism"))
		srp = User.objects.create_user(username="srp", password="srp-secret")
		srp.groups.add(Group.objects.create(name="store_requisition"))
		self.client = APIClient()
		self.client.credentials(HTTP_AUTHORIZATION="Basic cmVzdHJvd29ya3M6c2VjcmV0")  # restroworks:secret
		self.store = Store.objects.create(
			store_name="CR Adeniran", icg_warehouse_name="LAG, ADENIRAN", icg_warehouse_code="W101",
			byd_cost_center_code="4100003-17", pos_store_id="3727",
		)
		Store.objects.create(store_name="CR Ajah", icg_warehouse_code="I3", byd_cost_center_code="4100003-18", pos_store_id="3728")

	def push(self, **overrides):
		response = self.client.post("/api/v1/pos/sales", {**SALES_PAYLOAD, **overrides}, format="json")
		self.assertEqual(response.status_code, 200)
		return response.json()

	def feed(self, day, username="bp", password="bp-secret"):
		token = APIClient().post("/sales-feed/token", {"grant_type": "password", "username": username, "password": password})
		self.assertEqual(token.status_code, 200)
		reader = APIClient()
		reader.credentials(HTTP_AUTHORIZATION=f"Bearer {token.json()['access_token']}")
		return reader.get(f"/sales-feed/api/FoodConcept/Sales/{day}")

	def test_sales_are_stored_per_store_and_day(self):
		self.assertEqual(self.push(), {"Status": "Success"})
		sale = PosSale.objects.get()
		self.assertEqual(sale.store, self.store)
		self.assertEqual(sale.tenders, [
			{"paymentType": "CASH", "amount": "528300.00"},
			{"paymentType": "DEBIT CARD", "amount": "541700.50"},
			{"paymentType": "BANK TRANSFER", "amount": "149700.00"},
			{"paymentType": "CREDIT", "amount": "0.00"},
		])

	def test_a_later_push_replaces_the_day(self):
		self.push()
		self.push(tenders=[{"paymentType": "CASH", "amount": 600000}])
		sale = PosSale.objects.get()
		self.assertEqual(sale.tenders, [{"paymentType": "CASH", "amount": "600000.00"}])
		self.assertEqual(sale.pushes, 2)
		self.push(businessDate="2026-10-23")
		self.assertEqual(PosSale.objects.count(), 2)

	def test_unknown_store_and_bad_payload_fail_with_reason(self):
		body = self.push(storeId="9999")
		self.assertEqual(body["Status"], "Fail")
		self.assertIn("Unknown storeId", body["Reason"])
		body = self.push(businessDate="22/10/2026")
		self.assertEqual(body["Status"], "Fail")
		self.assertIn("businessDate", body["Reason"])
		self.assertEqual(PosSale.objects.count(), 0)

	def test_feed_matches_icg_sales_format(self):
		self.push()
		self.push(storeId="3728", tenders=[{"paymentType": "CASH", "amount": 305050}])
		response = self.feed("2026-10-22")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), [
			{"warehouseCode": "I3", "warehouseName": "CR Ajah", "date": "2026-10-22", "paymentType": "CASH", "amount": "305050"},
			{"warehouseCode": "W101", "warehouseName": "LAG, ADENIRAN", "date": "2026-10-22", "paymentType": "CASH", "amount": "528300"},
			{"warehouseCode": "W101", "warehouseName": "LAG, ADENIRAN", "date": "2026-10-22", "paymentType": "DEBIT CARD", "amount": "541700.5"},
			{"warehouseCode": "W101", "warehouseName": "LAG, ADENIRAN", "date": "2026-10-22", "paymentType": "BANK TRANSFER", "amount": "149700"},
		])
		self.assertEqual(self.feed("2026-10-21").json(), [])
		self.assertEqual(self.feed("21-10-2026").status_code, 400)

	def test_each_feed_is_limited_to_its_caller(self):
		# Only Blue Prism gets a sales feed token, and the SRP's token does not open the sales feed.
		self.assertEqual(APIClient().post("/sales-feed/token", {"grant_type": "password", "username": "srp", "password": "srp-secret"}).status_code, 400)
		self.assertEqual(APIClient().post("/sales-feed/token", {"grant_type": "password", "username": "bp", "password": "wrong"}).status_code, 400)
		srp_token = APIClient().post("/srp-feed/token", {"grant_type": "password", "username": "srp", "password": "srp-secret"}).json()["access_token"]
		reader = APIClient()
		reader.credentials(HTTP_AUTHORIZATION=f"Bearer {srp_token}")
		self.assertEqual(reader.get("/sales-feed/api/FoodConcept/Sales/2026-10-22").status_code, 403)
		# Blue Prism's token does not open the SRP feed or the rest of the API, and it cannot push sales.
		bp_token = APIClient().post("/sales-feed/token", {"grant_type": "password", "username": "bp", "password": "bp-secret"}).json()["access_token"]
		reader.credentials(HTTP_AUTHORIZATION=f"Bearer {bp_token}")
		self.assertEqual(reader.get("/srp-feed/api/FoodConcept/StoreRequest/2026-10-22").status_code, 403)
		self.assertEqual(reader.get("/api/v1/stores").status_code, 401)
		self.assertEqual(APIClient().post("/api/v1/pos/sales", SALES_PAYLOAD, format="json").status_code, 401)
		blue_prism = APIClient()
		blue_prism.force_authenticate(User.objects.get(username="bp"))
		self.assertEqual(blue_prism.post("/api/v1/pos/sales", SALES_PAYLOAD, format="json").status_code, 403)


class ByDClientTests(TestCase):

	def _response(self, status_code, body=None, headers=None, text=""):
		response = mock.Mock(status_code=status_code, headers=headers or {}, text=text, content=b"x")
		response.json.return_value = body or {}
		return response

	@mock.patch.dict(os.environ, {"SAP_URL": "https://my000000.sapbydesign.com"})
	@mock.patch("byd_services.rest.Session")
	def test_session_csrf_refresh_and_collections(self, session_class):
		from byd_services.rest import ByDClient
		session = session_class.return_value
		session.get.side_effect = [
			self._response(200, headers={"x-csrf-token": "T1"}),
			self._response(200, {"d": {"results": [{"ObjectID": "A1", "ReleaseStatusCode": "1"}]}}),
			self._response(200, headers={"x-csrf-token": "T2"}),
		]
		session.post.side_effect = [
			self._response(403, text="CSRF token validation failed"),
			self._response(201, {"d": {"results": {"ObjectID": "NEW"}}}),
		]
		client = ByDClient()
		self.assertEqual(client.find_inbound_delivery("RWG1")["ObjectID"], "A1")
		self.assertIn("$filter=ID eq 'RWG1'", session.get.call_args_list[1].args[0])
		self.assertEqual(client.create_inbound_delivery({"ID": "RWG1"}), {"ObjectID": "NEW"})
		self.assertEqual(session.post.call_args.kwargs["headers"]["x-csrf-token"], "T2")
