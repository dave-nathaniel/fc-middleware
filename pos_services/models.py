"""
Records of everything exchanged with the Restroworks POS.

PurchaseOrder      approved POS purchase orders (the demand signal handed to the
                   Store Requisition Portal) and the ByD documents they became.
PurchaseOrderLink  a ByD document (sales order, purchase request or purchase
                   order) created for a POS purchase order.
Dispatch           an invoice/dispatch we sent back to the POS for a purchase
                   order. The store's GRN is received against it.
InventoryTransaction  GRNs, returns to vendor and wastage pushed by the POS,
                   with their ByD posting status. This is our reconciliation log.
PosSale            a store's sales for one business date, by payment type, as
                   pushed by the POS. Blue Prism reads them through the sales feed.
"""
from django.db import models

from store_services.models import Store


class PurchaseOrder(models.Model):
	SUPPLY_DIRECT = "direct"      # external vendor: ByD purchase request -> purchase order
	SUPPLY_INTERNAL = "internal"  # Warehouse, CK or PPU: ByD sales order -> outbound delivery
	SUPPLY_CHOICES = [(SUPPLY_DIRECT, "Direct vendor"), (SUPPLY_INTERNAL, "Warehouse / CK / PPU")]

	po_id = models.CharField(max_length=64, unique=True, help_text="Restroworks poId.")
	prefix = models.CharField(max_length=64, blank=True)
	po_number = models.PositiveIntegerField()
	store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="pos_purchase_orders")
	customer_key = models.CharField(max_length=255, help_text="Restroworks outlet key, sent back on every invoice.")
	vendor_code = models.CharField(max_length=64)
	vendor_name = models.CharField(max_length=255, blank=True)
	supply_type = models.CharField(max_length=10, choices=SUPPLY_CHOICES)
	expected_delivery = models.DateTimeField(null=True, blank=True)
	items = models.JSONField(help_text="[{itemCode, itemName, quantity}] as approved in the POS.")
	payload = models.JSONField(help_text="The request exactly as received.")
	received_on = models.DateField(help_text="Business date (Africa/Lagos) the PO reached the middleware. SRP pulls by this date.")
	received_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-received_at"]
		indexes = [models.Index(fields=["received_on"])]

	@property
	def total_quantity(self):
		return sum(float(item["quantity"]) for item in self.items)

	def __str__(self):
		return f"{self.prefix}{self.po_number} | {self.store.store_name}"


class PurchaseOrderLink(models.Model):
	SALES_ORDER = "sales_order"
	PURCHASE_REQUEST = "purchase_request"
	PURCHASE_ORDER = "purchase_order"
	TYPE_CHOICES = [
		(SALES_ORDER, "ByD sales order"),
		(PURCHASE_REQUEST, "ByD purchase request"),
		(PURCHASE_ORDER, "ByD purchase order"),
	]

	purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="links")
	document_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
	document_id = models.CharField(max_length=64)
	# Quantities per item code that went into this ByD document, as reported by SRP.
	lines = models.JSONField(default=list, blank=True)
	# False once the document has been fully dispatched to the POS (stops polling it).
	open = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["purchase_order", "document_type", "document_id"], name="unique_po_link"),
		]

	def __str__(self):
		return f"{self.get_document_type_display()} {self.document_id}"


class Dispatch(models.Model):
	"""An invoice/dispatch sent to the POS (Restroworks 'save_purchase_order_invoice')."""
	PENDING, SENT, FAILED = "pending", "sent", "failed"
	STATUS_CHOICES = [(PENDING, "Pending"), (SENT, "Sent"), (FAILED, "Failed")]

	OUTBOUND_DELIVERY = "outbound_delivery"
	PURCHASE_ORDER = "purchase_order"
	SOURCE_CHOICES = [(OUTBOUND_DELIVERY, "ByD outbound delivery"), (PURCHASE_ORDER, "ByD purchase order")]

	purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="dispatches")
	invoice_no = models.CharField(max_length=64, unique=True)
	invoice_date = models.DateTimeField()
	source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
	source_id = models.CharField(max_length=64, help_text="ByD outbound delivery ID or purchase order ID.")
	# ByD details needed to post the GRN later: seller/ship-from party, and per item the
	# ByD unit code (and PO item reference for purchase orders).
	byd_context = models.JSONField(default=dict, blank=True)
	payload = models.JSONField(help_text="Body sent to Restroworks.")
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
	response = models.JSONField(null=True, blank=True)
	attempts = models.PositiveIntegerField(default=0)
	sent_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		constraints = [
			models.UniqueConstraint(fields=["purchase_order", "source_type", "source_id"], name="unique_dispatch_source"),
		]

	def __str__(self):
		return f"Invoice {self.invoice_no} for {self.purchase_order}"


class InventoryTransaction(models.Model):
	GRN, VENDOR_RETURN, WASTAGE = "grn", "vendor_return", "wastage"
	KIND_CHOICES = [(GRN, "Goods received (GRN)"), (VENDOR_RETURN, "Return to vendor"), (WASTAGE, "Wastage")]

	QUEUED, POSTING, POSTED, FAILED = "queued", "posting", "posted", "failed"
	STATUS_CHOICES = [
		(QUEUED, "Queued (or waiting to retry)"),
		(POSTING, "Posting now"),
		(POSTED, "Posted to ByD"),
		(FAILED, "Failed, needs attention"),
	]

	kind = models.CharField(max_length=20, choices=KIND_CHOICES)
	store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="pos_transactions")
	reference = models.CharField(max_length=64, help_text="POS transaction number (unique per store and kind).")
	transaction_date = models.DateTimeField(null=True, blank=True)
	dispatch = models.ForeignKey(Dispatch, null=True, blank=True, on_delete=models.PROTECT, related_name="transactions")
	purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="transactions")
	payload = models.JSONField(help_text="The request exactly as received.")
	data = models.JSONField(help_text="The validated request (codes as text, quantities as decimal strings). Posting reads this.")
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=QUEUED)
	byd_document_id = models.CharField(max_length=64, blank=True, help_text="ID of the ByD document we create (idempotency key).")
	byd_object_id = models.CharField(max_length=64, blank=True)
	error = models.TextField(blank=True)
	attempts = models.PositiveIntegerField(default=0)
	received_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	posted_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-received_at"]
		constraints = [
			models.UniqueConstraint(fields=["kind", "store", "reference"], name="unique_pos_transaction"),
		]

	def __str__(self):
		return f"{self.get_kind_display()} {self.reference} | {self.store.store_name}"


class PosSale(models.Model):
	"""
		A store's sales for one business date, by payment type, as last pushed by the POS.
		This is the raw sales record that replaces ICG as Blue Prism's source. Validated
		sales come back separately through POST /api/v1/sales (sales_aggregation).
	"""
	store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="pos_sales")
	business_date = models.DateField()
	tenders = models.JSONField(help_text='[{"paymentType": "CASH", "amount": "528300.00"}], one entry per payment type.')
	payload = models.JSONField(help_text="The latest request exactly as received.")
	pushes = models.PositiveIntegerField(default=1, help_text="How many times the POS has sent this store and date. A later push replaces the earlier one.")
	received_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-business_date", "store__icg_warehouse_code"]
		constraints = [
			models.UniqueConstraint(fields=["store", "business_date"], name="unique_pos_sale"),
		]
		indexes = [models.Index(fields=["business_date"])]

	@property
	def total(self):
		from decimal import Decimal
		return sum((Decimal(t["amount"]) for t in self.tenders), Decimal("0"))

	def __str__(self):
		return f"{self.store.store_name} | {self.business_date}"
