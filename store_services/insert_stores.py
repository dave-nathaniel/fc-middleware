import os, sys
import json
import django
from django.core.wsgi import get_wsgi_application
from django.db import IntegrityError
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "middleware.settings")

django.setup()

from .models import Store  # Replace with the actual name of your Django project

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "middleware.settings")  # Replace with the actual name of your Django project

application = get_wsgi_application()

data_file_path = 'store_services/store_data.json'  # Replace with the actual path to your data file

with open(data_file_path, 'r') as file:
	store_json = file.read()
	store_json = json.loads(store_json)

not_found = []
selected_stores = ["4100003-47", "4100003-12", "4100003-2", "4100003-18", "4100003-7", "4100003-20", "4100003-27", "4100003-23", "4100003-22", "4100003-10", "4100003-36", "4100003-24", "4100003-16", "4100003-15", "4100003-19", "4100003-33", "4100003-13", "4100003-1", "4100003-11", "4100003-21", "4100003-3", "4100003-17", "4100017-3", "4100008-6", "4100003-40", "4100013-4"]

all_stores = Store.objects.all()

for s in all_stores:
	if s.byd_cost_center_code in selected_stores:
		print(f"{s.store_name}")
		s.post_sale_to_byd = True
	else:
		s.post_sale_to_byd = False

	s.save()

sys.exit()

for s in store_json:
	target = Store.objects.filter(store_name__icontains=s)
	if len(target) > 0:
		of_store = target[0]
		# print(f"{s} => {of_store}")
		# print(f"{store_json[s]} => {of_store.icg_warehouse_code}")
		of_store.vat = 7.5
		of_store.consumption_tax = 5.0
		of_store.tourism_development_levy = 0.0
		of_store.marketing_fund_provision = 0.03
		of_store.locality_marketing_provision = 0.01
		of_store.mgmt_fee = 0.075
		of_store.mgmt_fee_share_service = 62.0
		of_store.mgmt_fee_development = 15.0
		of_store.mgmt_fee_hr = 23.0
		of_store.variable_rent = 0.0
		of_store.post_sale_to_byd = True

		print(f"{of_store.icg_warehouse_code}|{of_store.store_name}|{of_store.byd_cost_center_code}|-|{of_store.vat}|{of_store.consumption_tax}|{of_store.tourism_development_levy}|{of_store.marketing_fund_provision}|{of_store.locality_marketing_provision}|{of_store.mgmt_fee}|{of_store.variable_rent}")

		# of_store.save()
	else:
		not_found.append(s)

for nf in not_found:
	# n = nf.keys()[0]
	# print(store_json[nf])
	print(f"{store_json[nf]}|{nf}|-|-|7.5|-|-|0.03|0.01|0.075|-")
