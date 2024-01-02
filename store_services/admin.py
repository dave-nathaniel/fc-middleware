from django.contrib import admin
from .models import Store, Sales


class MyStoreAdmin(admin.ModelAdmin):
	search_fields = ['store_name', 'icg_warehouse_code', 'byd_cost_center_code', 'state']

class MySalesAdmin(admin.ModelAdmin):
	# readonly_fields = ('store', 'sales_data')
	search_fields = ['store__store_name', 'store__icg_warehouse_code', 'store__state']
	readonly_fields = ('store', 'sales_data', 'gross_total', 'water_sales', 'staff_meal', 'store_percentages', 'calculated_sales_data', )


# Register your models here.
admin.site.register(Store, MyStoreAdmin)
admin.site.register(Sales, MySalesAdmin)