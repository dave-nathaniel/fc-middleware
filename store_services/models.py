from django.db import models


class Store(models.Model):
	# Store identifiers
	store_name = models.CharField(max_length=255)
	store_email = models.EmailField(max_length=255, null=True, blank=True)
	icg_warehouse_name = models.CharField(max_length=255, null=True, blank=True)
	icg_warehouse_code = models.CharField(max_length=20, unique=True)
	icg_future_warehouse_code = models.CharField(max_length=20, null=True, blank=True)
	byd_cost_center_code = models.CharField(max_length=20)
	byd_sales_unit_id = models.CharField(max_length=20, null=True, blank=True)
	byd_bill_to_party_id = models.CharField(max_length=20, null=True, blank=True)
	byd_account_id = models.CharField(max_length=20, null=True, blank=True)
	byd_supplier_ck_id = models.CharField(max_length=20, null=True, blank=True)
	byd_supplier_ppu_id = models.CharField(max_length=20, null=True, blank=True)
	# Store sales and taxes
	vat = models.DecimalField(max_digits=5, decimal_places=2, default=7.5)
	consumption_tax = models.DecimalField(max_digits=5, decimal_places=2, default=0)
	tourism_development_levy = models.DecimalField(max_digits=5, decimal_places=2, default=0)
	marketing_fund_provision = models.DecimalField(max_digits=10, decimal_places=5, default=0)
	locality_marketing_provision = models.DecimalField(max_digits=10, decimal_places=5, default=0)
	mgmt_fee = models.DecimalField(max_digits=10, decimal_places=5, default=0.075)
	mgmt_fee_share_service = models.DecimalField(max_digits=10, decimal_places=5, default=62)
	mgmt_fee_development = models.DecimalField(max_digits=10, decimal_places=5, default=15)
	mgmt_fee_hr = models.DecimalField(max_digits=10, decimal_places=5, default=23)
	variable_rent = models.DecimalField(max_digits=10, decimal_places=5, default=0)
	# Store sync controls
	post_sale_to_byd = models.BooleanField(default=False)
	last_synced = models.DateField(null=True, blank=True)

	@property
	def store_type(self, ):
		types = {
			"cr": "Chicken Republic",
			"pie": "Pie Express",
			"chop": "Chop Box"
		}

		return types[self.store_name.lower().split(" ")[0]]

	def __str__(self):
		return f"{self.store_name.upper()} | {self.icg_warehouse_name.upper()}"
