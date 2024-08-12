import os
from dotenv import load_dotenv
import django
import pandas as pd
from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist

load_dotenv()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "middleware.settings")

django.setup()

from .models import Store 

# Load the Excel sheet into a DataFrame
excel_file_path = 'store_services/app_assets/STORE CONFIGURATION.xlsx'
df = pd.read_excel(excel_file_path, dtype=str)
df.fillna('', inplace=True)

errors = []
new_stores = []
updated = []

# Iterate through each row in the DataFrame
for index, row in df.iterrows():
	store_icg_warehouse_code = str(row['ICG Current Code']).strip()
	# Prepare data for Store model
	store_data = {
		# Store Properties
		'store_name': str(row['ByD Cost Centre Description']).strip(),
		'store_email': str(row['Store Email']).strip(),
		'icg_warehouse_name': str(row['ICG Warehouse Description']).strip(),
		'icg_warehouse_code': store_icg_warehouse_code,
		'icg_future_warehouse_code': str(row['ICG Future Code']).strip(),
		'byd_cost_center_code': str(row['ByD Cost Centre ID']).strip(),
		'byd_sales_unit_id': str(row['ByD SCD Warehouse ID']).strip(),
		'byd_bill_to_party_id': str(row['ByD Bill to Party ID']).strip(),
		'byd_account_id': str(row['ByD Account ID']).strip(),
		'byd_supplier_ck_id': str(row['ByD Supplier CK ID']).strip(),
		'byd_supplier_ppu_id': str(row['ByD Supplier PPU ID']).strip(),
		# Sales and Taxes
		'vat': Decimal(float(row['VAT'])*100),
		'consumption_tax': Decimal(float(row['Consumption Tax'])*100),
		'tourism_development_levy': Decimal(float(row['Tourism Tax'])*100),
		'locality_marketing_provision': Decimal(float(row['Locality Marketing Provision'])),
		'marketing_fund_provision': Decimal(float(row['Marketing Fund Provision'])),
		'mgmt_fee': Decimal(float(row['Management Fee'])),
		'mgmt_fee_share_service': Decimal('62.00000'),
		'mgmt_fee_development': Decimal('15.00000'),
		'mgmt_fee_hr': Decimal('23.000'),
	}

	# Create or update the Store model
	try:
		try:
			store = Store.objects.get(icg_warehouse_code=store_icg_warehouse_code)
			store_data.pop('icg_warehouse_code')
			for key, value in store_data.items():
				setattr(store, key, value)
			store.save()
			updated.append(store)
			print(f"Updated: {store}")
		except ObjectDoesNotExist:
			print(f"ICG Warehouse: {store_icg_warehouse_code} does not exist. Creating new record.")
			store = Store(**store_data)
			store.save()
			new_stores.append(store)
	except Exception as e:
		errors.append(f"{row['ICG Warehouse Description']}: {e} \n {row}")
		continue
		
print("\nSummary:")
print(f"Created: {len(new_stores)}")
print(f"Updated: {len(updated)}")
print(f"Errors: {len(errors)}")
print("\n".join(errors))