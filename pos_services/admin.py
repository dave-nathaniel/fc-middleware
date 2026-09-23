"""
Admin views double as the reconciliation screens on our side: every POS push,
its ByD document and posting status, and every invoice sent back to the POS.
"""
from django.contrib import admin, messages

from .models import PurchaseOrder, PurchaseOrderLink, Dispatch, InventoryTransaction


class PurchaseOrderLinkInline(admin.TabularInline):
	model = PurchaseOrderLink
	extra = 0
	fields = ["document_type", "document_id", "lines", "open", "created_at"]
	readonly_fields = ["created_at"]
	verbose_name = "ByD document"
	verbose_name_plural = "ByD documents (add a ByD purchase order here once procurement has created it from the purchase request)"


class DispatchInline(admin.TabularInline):
	model = Dispatch
	extra = 0
	can_delete = False
	fields = ["invoice_no", "source_type", "source_id", "status", "sent_at"]
	readonly_fields = fields
	show_change_link = True


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
	list_display = ["__str__", "vendor_code", "vendor_name", "supply_type", "received_on", "linked", "invoiced"]
	list_filter = ["supply_type", "received_on", "store"]
	search_fields = ["po_id", "prefix", "po_number", "vendor_code", "vendor_name", "store__store_name", "store__pos_store_id"]
	readonly_fields = [f.name for f in PurchaseOrder._meta.fields]
	inlines = [PurchaseOrderLinkInline, DispatchInline]

	@admin.display(boolean=True)
	def linked(self, obj):
		return obj.links.exists()

	@admin.display(boolean=True)
	def invoiced(self, obj):
		return obj.dispatches.filter(status=Dispatch.SENT).exists()


@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
	list_display = ["invoice_no", "purchase_order", "source_type", "source_id", "status", "attempts", "sent_at"]
	list_filter = ["status", "source_type"]
	search_fields = ["invoice_no", "source_id", "purchase_order__po_id", "purchase_order__po_number"]
	readonly_fields = [f.name for f in Dispatch._meta.fields]
	actions = ["resend"]

	@admin.action(description="Send selected invoices to Restroworks again")
	def resend(self, request, queryset):
		from .tasks import send_dispatch
		for dispatch in queryset.exclude(status=Dispatch.SENT):
			send_dispatch.delay(dispatch.pk)
		messages.info(request, "Queued the unsent invoices for sending.")


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
	list_display = ["reference", "kind", "store", "transaction_date", "status", "byd_document_id", "attempts", "received_at", "posted_at"]
	list_filter = ["kind", "status", "store"]
	search_fields = ["reference", "byd_document_id", "byd_object_id", "store__store_name", "store__pos_store_id"]
	readonly_fields = [f.name for f in InventoryTransaction._meta.fields]
	actions = ["retry"]

	@admin.action(description="Retry posting the selected transactions to ByD")
	def retry(self, request, queryset):
		from .tasks import post_transaction
		count = 0
		for txn in queryset.exclude(status=InventoryTransaction.POSTED):
			post_transaction.delay(txn.pk)
			count += 1
		messages.info(request, f"Queued {count} transaction(s) for posting.")
