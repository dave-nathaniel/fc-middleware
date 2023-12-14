import os
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

data_file_path = 'store_services/store_data.txt'  # Replace with the actual path to your data file

with open(data_file_path, 'r') as file:
	for line in file:
		# Split the line into individual pieces using the pipe (|) as a separator
		state, store_name, icg_warehouse_code, byd_cost_center_code = map(str.strip, line.strip().split('|'))

		# Create a new Store object and save it to the database
		try:
			Store.objects.create(
				state=state,
				store_name=store_name,
				icg_warehouse_code=icg_warehouse_code,
				byd_cost_center_code=byd_cost_center_code
			)
			print(f"Successfully inserted data for {store_name}")
		except IntegrityError:
			print(f"Data for {store_name} already exists. Skipping.")

print("Data insertion complete.")
