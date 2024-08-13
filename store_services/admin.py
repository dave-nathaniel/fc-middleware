from django.contrib import admin
from .models import Store


class MyStoreAdmin(admin.ModelAdmin):
	search_fields = ['store_name', 'icg_warehouse_name', 'icg_warehouse_code', 'byd_cost_center_code']
	readonly_fields = ('store_name', 'icg_warehouse_name', 'icg_warehouse_code', 'byd_cost_center_code', 'last_synced')

# Register your models here.
admin.site.register(Store, MyStoreAdmin)