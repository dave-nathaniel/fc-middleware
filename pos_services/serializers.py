"""
Request schemas for the Restroworks POS pushes.

PO, GRN and vendor return follow the Restroworks "ERP PO Process" document.
Wastage has no Restroworks schema; WastageSerializer is the schema we publish.
Unknown extra fields are accepted and kept in the stored payload.
"""
from decimal import Decimal

from rest_framework import serializers


class BatchSerializer(serializers.Serializer):
	quantity = serializers.DecimalField(max_digits=14, decimal_places=4)
	expiryDate = serializers.DateTimeField(required=False)
	batchNumber = serializers.CharField(required=False, allow_blank=True)


# ----------------------------------------------------------------------------
# 1) Purchase order submission
# ----------------------------------------------------------------------------
class VendorSerializer(serializers.Serializer):
	name = serializers.CharField(required=False, allow_blank=True)
	code = serializers.CharField()


class PurchaseOrderItemSerializer(serializers.Serializer):
	itemName = serializers.CharField(required=False, allow_blank=True)
	itemCode = serializers.CharField()
	quantity = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=Decimal("0.0001"))


class PurchaseOrderSerializer(serializers.Serializer):
	storeId = serializers.CharField()
	customerKey = serializers.CharField()
	expectedDelivery = serializers.DateTimeField(required=False)
	prefix = serializers.CharField(required=False, allow_blank=True, default="")
	poNumber = serializers.IntegerField(min_value=0)
	poId = serializers.CharField()
	vendor = VendorSerializer()
	items = PurchaseOrderItemSerializer(many=True, allow_empty=False)


# ----------------------------------------------------------------------------
# 3) GRN (stock entry)
# ----------------------------------------------------------------------------
class GRNItemSerializer(serializers.Serializer):
	itemCode = serializers.CharField()
	itemName = serializers.CharField(required=False, allow_blank=True)
	quantity = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=Decimal("0"))
	batches = BatchSerializer(many=True, required=False)


class GRNSerializer(serializers.Serializer):
	customerKey = serializers.CharField(required=False, allow_blank=True)
	storeId = serializers.CharField()
	invoiceNo = serializers.CharField()
	invoiceDate = serializers.DateTimeField(required=False)
	transactionNumber = serializers.CharField()
	transactionDate = serializers.DateTimeField()
	items = GRNItemSerializer(many=True, allow_empty=False)


# ----------------------------------------------------------------------------
# 4) Local stock return (return to vendor)
# ----------------------------------------------------------------------------
class VendorReturnItemSerializer(serializers.Serializer):
	code = serializers.CharField()
	name = serializers.CharField(required=False, allow_blank=True)
	quantity = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=Decimal("0.0001"))
	batches = BatchSerializer(many=True, required=False)


class VendorReturnSerializer(serializers.Serializer):
	storeId = serializers.CharField()
	poPrefix = serializers.CharField(required=False, allow_blank=True, default="")
	poNumber = serializers.IntegerField(min_value=0)
	returnPrefix = serializers.CharField(required=False, allow_blank=True, default="")
	returnTransactionNo = serializers.CharField()
	returnDate = serializers.DateTimeField(required=False)
	items = VendorReturnItemSerializer(many=True, allow_empty=False)


# ----------------------------------------------------------------------------
# 5) Wastage (schema defined by the middleware)
# ----------------------------------------------------------------------------
class WastageItemSerializer(serializers.Serializer):
	itemCode = serializers.CharField()
	itemName = serializers.CharField(required=False, allow_blank=True)
	quantity = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=Decimal("0.0001"))
	unitCode = serializers.CharField(help_text="ByD unit of measure code, e.g. KGM, EA, LTR.")
	unitCost = serializers.DecimalField(max_digits=14, decimal_places=4, required=False)
	subTotal = serializers.DecimalField(max_digits=16, decimal_places=4, required=False)
	reasonCode = serializers.CharField()
	reasonDescription = serializers.CharField(required=False, allow_blank=True)
	stage = serializers.ChoiceField(choices=["raw", "wip", "finished"], required=False)
	batches = BatchSerializer(many=True, required=False)


class WastageSerializer(serializers.Serializer):
	storeId = serializers.CharField()
	customerKey = serializers.CharField(required=False, allow_blank=True)
	wastagePrefix = serializers.CharField(required=False, allow_blank=True, default="")
	wastageNumber = serializers.CharField()
	wastageDate = serializers.DateTimeField()
	tradingDate = serializers.DateField(required=False)
	recordedBy = serializers.CharField()
	approvedBy = serializers.CharField(required=False, allow_blank=True)
	items = WastageItemSerializer(many=True, allow_empty=False)


# ----------------------------------------------------------------------------
# SRP -> middleware: ByD documents created by demand planning
# ----------------------------------------------------------------------------
class LinkLineSerializer(serializers.Serializer):
	warehouse = serializers.CharField(help_text="Store ICG warehouse code as held on the SRP item line.")
	series = serializers.CharField(allow_blank=True)
	orderID = serializers.IntegerField()
	reference = serializers.CharField(help_text="Item code.")
	quantity = serializers.DecimalField(max_digits=14, decimal_places=4)


class LinkSerializer(serializers.Serializer):
	document_type = serializers.ChoiceField(choices=["sales_order", "purchase_request", "purchase_order"])
	document_id = serializers.CharField()
	lines = LinkLineSerializer(many=True, allow_empty=False)


def first_error(errors):
	"""Flattens DRF validation errors into one readable sentence for the POS monitor."""
	def walk(node, path):
		if isinstance(node, dict):
			for key, value in node.items():
				yield from walk(value, f"{path}.{key}" if path else key)
		elif isinstance(node, list):
			for index, value in enumerate(node):
				if isinstance(value, (dict, list)):
					yield from walk(value, f"{path}[{index}]")
				else:
					yield f"{path}: {value}"
	messages = list(walk(errors, ""))
	return "; ".join(messages[:5]) or "Invalid request."
