from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from store_services.models import Store
from core_services.cryptography import CryptoTools
from core_services.models import KeyStore
import simplejson as sjson

User = get_user_model()
crypto_tools = CryptoTools()

# Create your models here.
class LedgerAccount(models.Model):
	name = models.CharField(max_length=255)
	description = models.TextField()
	canonical_name = models.CharField(max_length=255, null=True, blank=True)
	byd_gl_code = models.CharField(max_length=20)

	def __str__(self,):
		return self.name


to_float = lambda x: round(float(sjson.dumps(x)),2)# Lamda function to convert JSON to float

class Sale(models.Model):
	'''
		Model to store sales data.
	'''
	# The store to which this sale belongs.
	store = models.ForeignKey(Store, on_delete=models.CASCADE)
	# The user who posted this sale.
	posted_by = models.ForeignKey(User, on_delete=models.CASCADE)
	# The gross sale amount which has been reconciled.
	reconciled_gross_total = models.FloatField(blank=False, null=False)
	# The outstanding sale amount which has not been reconciled.
	outstanding_gross_total = models.FloatField(blank=False, null=False, default=0.0)
	# The date which this sale was made.
	sale_date = models.DateField(auto_now_add=False)
	# The signature of the user on the sale data posted.
	signature = models.TextField(null=False, blank=False)
	# The timestamp which this record was added or last modified.
	modified = models.DateTimeField(auto_now=True)
	# Extra metadata related to this sale.
	metadata = models.JSONField(null=True, blank=True)
	# A hash of the data used to calculate the sales data.
	hash_digest = models.CharField(max_length=255, blank=False, null=False)
	# defined store percentages at the time of posting this sale, used for calculating the sales data.
	store_percentages = models.JSONField(null=False, blank=False)
	# Calculated sales data based on the percentages defined for this store.
	calculated_sales_data = models.JSONField(null=False, blank=False)
	# Bool indicating whether this sale has been posted to BOD. 0 - Not posted, 1
	posted_to_byd = models.BooleanField(default=False)
	# The date when this sale was posted to BOD.
	date_posted = models.DateTimeField(null=True, blank=True)
	
	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['reconciled_gross_total', 'store', 'sale_date'], name='unique_sales')
		]
	
	@property
	def sale_identity(self,) -> tuple:
		'''
			This property generates a unique identifier for each sale.
			It combines the reconciled gross total, outstanding gross total, sale date, and store ICG warehouse code.
		'''
		identity = f"{self.reconciled_gross_total}{self.outstanding_gross_total}{self.sale_date}{self.store.icg_warehouse_code}"
		id_digest = crypto_tools.create_digest(identity)
		return identity, id_digest
	
	def signature_valid(self, ) -> bool:
		'''
			Validate that the signature provided is valid (i.e. the sale identity was signed by the user who created the sale).
			The signature is verified using the user's public key.
		'''
		# The signature
		signature = self.signature
		# The data that was signed.
		data = self.sale_identity[1]
		# The user's public key from the user's keystore.
		user_keystore = KeyStore.objects.get(user=self.posted_by)
		user_public_key = crypto_tools.load_public_key(user_keystore.public_key)
		# Verify the signature using the user's public key.'
		return crypto_tools.signature_valid(user_public_key, signature, data)
	
	def data_valid(self, ) -> bool:
		'''
			Validate that the data provided is valid (i.e. the hash digest matches the calculated hash digest).
			The data is verified using the user's private key.
		'''
		# Recalculate the hash digest.
		data_digest = self.generate_hash_digest()
		# Is the hash_digest equal to the re-calculated hash digest?
		return self.hash_digest == data_digest.hexdigest()

	def set_sales_data(self, ):
		'''
			This method calculates the sales data based on the percentages defined for this store.
		'''
		# The gross sale amount.
		gross_sale = to_float(self.reconciled_gross_total)
		
		# Convert the tax percentages from decimal to float.
		store_vat = to_float(self.store.vat)
		consumption_tax = to_float(self.store.consumption_tax)
		tourism_development_levy = to_float(self.store.tourism_development_levy)
		# The denominators for calculating sales tax.
		tax_denominator = 100 + store_vat + consumption_tax + tourism_development_levy
		# Calculate the sales tax.
		vat = store_vat / tax_denominator * gross_sale
		# A dictionary to store the calculated sales data.
		calculated_sales_data = {
			"vat": vat,
			"consumption_tax": to_float(((gross_sale - vat) / (100 + consumption_tax)) * consumption_tax),
			"tourism_development_levy": to_float(((gross_sale - vat) / (100 + tourism_development_levy)) * tourism_development_levy),
		}
		# Calculate the sum of all the taxes on the gross sale.
		sales_tax = sum(calculated_sales_data.values())
		calculated_sales_data["sales_tax"] = sales_tax
		# The net sale amount after all taxes have been deducted.
		net_sales = gross_sale - sales_tax
		calculated_sales_data["net_sales"] = net_sales
		
		'''Marketing fund provision is calculated based on the net sale amount.'''
		# Convert from decimal to float for calculation.
		marketing_fund_provision = to_float(self.store.marketing_fund_provision)
		locality_marketing_provision = to_float(self.store.locality_marketing_provision)
		# Calculate the marketing fund provision and add it to the calculated sales data.
		calculated_sales_data["marketing_fund_provision"] = net_sales * marketing_fund_provision
		calculated_sales_data["locality_marketing_provision"] = net_sales * locality_marketing_provision
		
		'''Management fee is calculated based on the net sale amount.'''
		# Convert from decimal to float for calculation.
		store_mgmt_fee = to_float(self.store.mgmt_fee)
		mgmt_fee_share_service = to_float(self.store.mgmt_fee_share_service)
		mgmt_fee_development = to_float(self.store.mgmt_fee_development)
		mgmt_fee_hr = to_float(self.store.mgmt_fee_hr)
		# Calculate the management fee and add it to the calculated sales data.
		mgmt_fee = net_sales * store_mgmt_fee
		calculated_sales_data["mgmt_fee"] = mgmt_fee
		calculated_sales_data["mgmt_fee_share_service"] = (mgmt_fee_share_service * mgmt_fee) / 100
		calculated_sales_data["mgmt_fee_development"] = (mgmt_fee_development * mgmt_fee) / 100
		calculated_sales_data["mgmt_fee_hr"] = (mgmt_fee_hr * mgmt_fee) / 100
		
		# Variable rent is calculated based on the net sale amount.
		variable_rent = to_float(self.store.variable_rent)
		calculated_sales_data["variable_rent"] = 0.00
		
		# Round the figures to three decimal places and set the calculated sales data.
		self.calculated_sales_data = {k: round(v, 2) for k, v in calculated_sales_data.items()}
	
	def get_store_percentages(self, ) -> dict:
		'''
			Returns the percentages at the time of creation, defined for the store that made this sale.
		'''
		return {
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
	
	def get_sales_data(self,) -> dict:
		'''
			Returns the calculated sales data based on the percentages defined for the store that made this sale.
		'''
		if not self.calculated_sales_data:
			self.set_sales_data()
		return self.calculated_sales_data
	
	def generate_hash_digest(self, ):
		'''
			Calculate and set the hash digest for the sale data.
			The hash digest is a concatenation of the 'sale_identity' + the 'calculated_sales_data' + the 'store_percentages' + the 'modified' timestamp.
		'''
		import json
		sale_identity = self.sale_identity[0]
		# Convert the calculated sales data disctionary into a JSON string.
		calculated_sales_data = json.dumps(self.get_sales_data())
		# Convert the store percentages dictionary into a JSON string.
		store_percentages = json.dumps(self.store_percentages)
		# Create the hash digest using the sale identity, calculated sales data, and store percentages.
		data = f"{sale_identity}{calculated_sales_data}{store_percentages}{self.modified}"
		# Create and return the hash digest using the crypto_tools.create_digest method.
		return crypto_tools.create_digest(data)
	
	def clean(self, ):
		'''
			Validate the sale data before saving it to the database.
		'''
		if not self.signature_valid():
			# If the signature is not valid, raise an error.
			raise ValueError("Invalid signature")

	def save(self, *args, **kwargs):
		'''
			Perform validation checks then save the sale to the database.
			Sales can only be created, not updated.
		'''
		if not self.pk:
			self.clean()
			# Calculate the sales data, and store percentages.
			self.set_sales_data()
			# Set the store percentages.
			self.store_percentages = self.get_store_percentages()
			# Generate and set the hash digest for the sale data.
			self.hash_digest = self.generate_hash_digest().hexdigest()
			# Save the sale to the database.
			return super(Sale, self).save(*args, **kwargs)
		# If the sale is being updated, raise an error.
		raise ValueError("Sales can only be created, not updated.")
	
	def __str__(self):
		return f"{self.store.store_name} SALES ON {self.sale_date} | <Signature: {'VALID' if self.signature_valid() else 'INVALID'}> | <Integrity: {'INTACT' if self.data_valid() else 'TAMPERED'}>"
	
@receiver(post_save, sender=Sale)
def update_digest(sender, instance, created, **kwargs):
	"""
		Signal handler to update the digest after the model is saved.
	"""
	# Calculate the new digest
	if created:
		instance.hash_digest = instance.generate_hash_digest().hexdigest()
		# Recalculate the digest to include the time that the original record was created.
		# Use update_fields to avoid triggering another post_save signal
		return super(Sale, instance).save(update_fields=['hash_digest'])
	return