import django
import os, sys
import logging
import time
import json
from pprint import pprint
from datetime import date, datetime
from django.utils import timezone
from icg_services.sales_data import ICGSalesData
from django.core.wsgi import get_wsgi_application
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from .posting import format_and_post

django.setup()

from store_services.models import Store, Sales
from .reporting import generate_excel_report


class Sync:

	icg_sales = ICGSalesData()

	def __init__(self, ):
		self.data = []
		self.save_records = False
		self.post_to_byd = False
		self.active_stores_only = True

	def set_save_records(self, save_records):
		self.save_records = save_records

	def set_post_to_byd(self, post_to_byd):
		self.post_to_byd = post_to_byd

	def set_stores_to_use(self, active_stores_only):
		self.active_stores_only = active_stores_only

	def set_sales_records(self, records):
		self.data = records

	def get_sales_from_icg(self, date=None):
		logging.info(f"Using sales records from ICG.")
		self.set_sales_records(self.icg_sales.get_sales(date)) #YYYY-MM-DD

	def get_sales_from_file(self, path):
		logging.info(f"Using sales records from data file: {path}")
		try:
			with open(path, 'r') as data:
				sales_data = data.read()
			self.set_sales_records(json.loads(sales_data))
		except Exception as e:
			logging.error(f"An error occurred while reading the data file: {e}")

	def do_sync(self,):

		data = self.data

		if data:
			grouped_data = self.icg_sales.group_data_by_warehouse(data)
			synced_sales = []
			missing_sales = []
			stores_to_use = Store.objects.filter(post_sale_to_byd=True) if self.active_stores_only else Store.objects.all()

			logging.info(f"Processing {len(stores_to_use)} selected stores.")

			for store in stores_to_use:
				warehouse = store.icg_warehouse_code
				sale = grouped_data.get(warehouse)

				if sale:
					'''
						This is the main purpose of this program.
					'''
					staff_meal = 0.00
					water_sales = 0.00
					data_date = ""

					logging.info(f"{'*' * 20}")
					logging.info(f"Store: {store.store_name} ({warehouse})")
					logging.info(f"Gross Total: {sale['total_amount']}")

					for item in sale['items']:
						data_date = item['date'] if data_date is not None else data_date
						logging.debug(item)
						if item['paymentType'] == 'STAFF MEAL':
							staff_meal = float(item['amount'])
							logging.debug(f"{store.store_name} Staff Meal: {staff_meal}")

					data_date = datetime.strptime(data_date, "%Y-%m-%d").date()

					try:
						total_amount = sale['total_amount']

						sales_data = Sales(
							store=store,
							sales_data=sale['items'],
							gross_total=total_amount,
							water_sales=water_sales,
							staff_meal=staff_meal,
							date=data_date,
						)

						computed_sales_data = sales_data.calculate()

						if self.save_records:
							store.last_synced = data_date
							store.save()
							sales_data.save()
							logging.info(f"Sales data for {store.store_name} saved successfully.")
						
					except Exception as e:
						logging.error(f"An error occurred while saving the computed data for '{store.store_name}': {e}")

					if self.post_to_byd:
						try:
							logging.info("Sending to ByD.")
							non_zero_values = {key: value for key, value in computed_sales_data.items() if value > 0.00}
							if format_and_post(data_date, store, non_zero_values, gross_total=total_amount):
								logging.info("Posting to SAP ByD completed successfully.")
								sales_data.posted_to_byd = True
								sales_data.save()
							else:
								logging.warn("An error may have occurred while posting some entries to SAP ByD. More information on this error can be found in the process logs.")

							synced_sales.append(sales_data)

						except Exception as e:
							logging.error(f"Something went wrong while posting to ByD for this store: {e}")
				else:
					missing_sales.append(store)
					continue

			#count_ = len()
			count_stores_to_use = len(stores_to_use)
			count_synced_sales = len(synced_sales)
			count_missing_sales = len(missing_sales)

			generate_excel_report(synced_sales, 'Sales_Aggregation_Report') if (count_synced_sales > 0) else None

			logging.info(f"{count_stores_to_use} stores selected for synchronization.")
			logging.info(f"{count_synced_sales} stores completed successfully.") if count_synced_sales else None
			if count_missing_sales:
				logging.error(f"The following {count_missing_sales} selected store(s) did not return sales data: \n{chr(10).join(['[!] ' + bad.store_name + ' (' + bad.icg_warehouse_name + ') ' for bad in missing_sales])}")
			logging.info(f"{(count_synced_sales*100)/count_stores_to_use}% of stores were posted to ByD.")

			logging.info("Completed sync.")

		else:
			logging.error(f"An error occurred fetching data from ICG. More information on this error can be found in the process logs.")

	logging.info("\n\n\n\n")