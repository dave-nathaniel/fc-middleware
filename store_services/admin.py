from django.contrib import admin
from .models import Store, Sales


class MySalesAdmin(admin.ModelAdmin):
	# readonly_fields = ('store', 'sales_data')
	search_fields = ['store__store_name', 'store__icg_warehouse_code', 'store__state']
	readonly_fields = ('store', 'sales_data', 'gross_total', 'water_sales', 'staff_meal', 'store_percentages', 'calculated_sales_data', )


# Register your models here.
admin.site.register(Store)
admin.site.register(Sales, MySalesAdmin)