import os, sys
from dotenv import load_dotenv
import django
from pprint import pprint
import pandas as pd
from decimal import Decimal

load_dotenv()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "middleware.settings")

django.setup()

from .models import Store 

# Load the Excel sheet into a DataFrame
excel_file_path = 'store_services/app_assets/STORE CONFIGURATION UPDATED.xlsx'
df = pd.read_excel(excel_file_path)

errors = []
new_stores = []
updated = []

# Iterate through each row in the DataFrame
for index, row in df.iterrows():

	# Prepare data for Store model
	store_data = {
		'store_name': str(row['ByD Cost Centre Description']),
		'icg_warehouse_name': row['ICG Warehouse Description'],
		'icg_warehouse_code': str(row['ICG Code']),
		'byd_cost_center_code': str(row['ByD Cost Centre ID']),
		'vat': Decimal(str(row['VAT']*100)),
		'consumption_tax': Decimal(str(row['Consumption Tax']*100)),
		'tourism_development_levy': Decimal(str(row['Tourism Tax']*100)),
		'locality_marketing_provision': Decimal(str(row['Locality Marketing Provision'])),
		'marketing_fund_provision': Decimal(str(row['Marketing Fund Provision'])),
		'mgmt_fee': Decimal(str(row['Management Fee'])),
		'mgmt_fee_share_service': Decimal('62.00000'),
		'mgmt_fee_development': Decimal('15.00000'),
		'mgmt_fee_hr': Decimal('23.000'),
	}

	# Create or update the Store model
	try:
		store = Store.objects.get(
			icg_warehouse_code=row['ICG Code']
		)

		store.store_email = row['Store Email'].strip()
		store.save()

		# new_stores.append(store) if created else updated.append(store)

	except Exception as e:
		errors.append(f"{row['ICG Warehouse Description']}: {e} \n {row}")
		continue

print(f"Created: {len(new_stores)}")
print(f"Updated: {len(updated)}")
print(f"Errors: {len(errors)}")
print("\n".join(errors))