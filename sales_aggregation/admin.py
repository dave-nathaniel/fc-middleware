from django.contrib import admin
from .models import LedgerAccount
from .models import Sale

class MySalesAdmin(admin.ModelAdmin):
	search_fields = ['store__store_name', 'store__icg_warehouse_code', 'store__icg_warehouse_name', 'store__byd_cost_center_code']
	readonly_fields = ("store","posted_by","reconciled_gross_total","outstanding_gross_total","sale_date","signature","modified","metadata","hash_digest","store_percentages","calculated_sales_data","posted_to_byd","date_posted")


# Register your models here.
admin.site.register(Sale, MySalesAdmin)
admin.site.register(LedgerAccount)