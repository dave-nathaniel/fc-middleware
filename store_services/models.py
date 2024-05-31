from decimal import Decimal
import simplejson as sjson
from django.db import models


to_float = lambda x: float(sjson.dumps(x))

class Store(models.Model):
	store_name = models.CharField(max_length=255)
	store_email = models.EmailField(max_length=255, null=True, blank=True)
	icg_warehouse_name = models.CharField(max_length=255, null=True, blank=True)
	icg_warehouse_code = models.CharField(max_length=20, unique=True)
	byd_cost_center_code = models.CharField(max_length=20, unique=True)
	byd_sales_unit_id = models.CharField(max_length=20, null=True, blank=True)
	byd_bill_to_party_id = models.CharField(max_length=20, null=True, blank=True)
	byd_account_id = models.CharField(max_length=20, null=True, blank=True)
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


class Sales(models.Model):
	store = models.ForeignKey(Store, on_delete=models.CASCADE)
	sales_data = models.JSONField()
	gross_total = models.DecimalField(max_digits=10, decimal_places=2)
	water_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
	staff_meal = models.DecimalField(max_digits=10, decimal_places=2)
	store_percentages = models.JSONField(null=True, blank=True)
	calculated_sales_data = models.JSONField(null=True, blank=True)
	date = models.DateField(auto_now_add=False)
	last_modified = models.DateTimeField(auto_now=True)
	posted_to_byd = models.BooleanField(default=False)

	def gross_sale_after_water(self,):
		return self.gross_total - self.water_sales

	def calculate(self, ):
		tax_denominator = 100 + self.store.vat + self.store.consumption_tax + self.store.tourism_development_levy

		gross_sale_after_water = Decimal(str(self.gross_sale_after_water()))
		vat = self.store.vat / tax_denominator * gross_sale_after_water

		calculated_sales_data = {
			"vat": to_float(vat),
			"consumption_tax": to_float(((gross_sale_after_water - vat) / (100 + self.store.consumption_tax)) * self.store.consumption_tax),
			"tourism_development_levy": to_float(((gross_sale_after_water - vat) / (100 + self.store.tourism_development_levy)) * self.store.tourism_development_levy),
			"marketing_fund_provision": 0.00,
			"locality_marketing_provision": 0.00,
			"mgmt_fee": 0.00,
			"mgmt_fee_share_service": 0.00,
			"mgmt_fee_development": 0.00,
			"mgmt_fee_hr": 0.00,
			"variable_rent": 0.00,
		}

		sales_tax = sum(calculated_sales_data.values())
		net_sales = self.gross_total - sales_tax

		calculated_sales_data["sales_tax"] = sales_tax
		calculated_sales_data["net_sales"] = net_sales
		calculated_sales_data["marketing_fund_provision"] = net_sales * to_float(self.store.marketing_fund_provision)
		calculated_sales_data["locality_marketing_provision"] = net_sales * to_float(self.store.locality_marketing_provision)

		mgmt_fee = net_sales * to_float(self.store.mgmt_fee)
		calculated_sales_data["mgmt_fee"] = mgmt_fee
		calculated_sales_data["mgmt_fee_share_service"] = (to_float(self.store.mgmt_fee_share_service) * mgmt_fee) / 100
		calculated_sales_data["mgmt_fee_development"] = (to_float(self.store.mgmt_fee_development) * mgmt_fee) / 100
		calculated_sales_data["mgmt_fee_hr"] = (to_float(self.store.mgmt_fee_hr) * mgmt_fee) / 100

		self.calculated_sales_data = calculated_sales_data

		return calculated_sales_data

	def save(self, *args, **kwargs):

		self.store_percentages = {
			"vat_percentage": to_float(self.store.vat),
			"consumption_tax_percentage":  to_float(self.store.consumption_tax),
			"tourism_development_levy_percentage": to_float(self.store.tourism_development_levy),
			"marketing_fund_provision_percentage": to_float(self.store.marketing_fund_provision),
			"locality_marketing_provision_percentage": to_float(self.store.locality_marketing_provision),
			"mgmt_fee_percentage": to_float(self.store.mgmt_fee),
			"mgmt_fee_share_service_percentage": to_float(self.store.mgmt_fee_share_service),
			"mgmt_fee_development_percentage": to_float(self.store.mgmt_fee_development),
			"mgmt_fee_hr_percentage": to_float(self.store.mgmt_fee_hr),
			"variable_rent_percentage": to_float(self.store.variable_rent),
		}

		super(Sales, self).save(*args, **kwargs)

	def __str__(self):
		return f"{self.store.store_name} SALES ON {self.date}"