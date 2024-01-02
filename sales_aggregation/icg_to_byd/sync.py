import django
import os, sys
import logging
import time
from pprint import pprint
from datetime import date, datetime
from django.utils import timezone
from icg_services.sales_data import ICGSalesData
from django.core.wsgi import get_wsgi_application
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

	def set_save_records(self, save_records):
		self.save_records = save_records

	def set_post_to_byd(self, post_to_byd):
		self.post_to_byd = post_to_byd

	def get_sales_from_icg(self, date=None):
		self.data = self.icg_sales.get_sales(date) #YYYY-MM-DD

	def get_sales_from_file(self, path):
		import json
		try:
			with open(path, 'r') as data:
				sales_data = data.read()

			sales_data = json.loads(sales_data)
			self.data = sales_data
		except Exception as e:
			logging.error(f"An error occurred while reading the data file: {e}")

	def do_sync(self,):

		data = self.data

		synced_sales = []

		if data:
			grouped_data = self.icg_sales.group_data_by_warehouse(data)
			
			# Print the grouped data
			for warehouse, sale in grouped_data.items():

				try:
					store = Store.objects.get(icg_warehouse_code=warehouse)
				except Exception as e:
					logging.error(f"Couldn't fetch Store information ({warehouse}): {e}")
					continue

				staff_meal = 0.00
				water_sales = 0.00
				data_date = ""

				logging.info(f"{'*' * 20}")
				logging.info(f"Store: {store.store_name}")
				logging.info(f"Gross Total: {sale['total_amount']}")

				for item in sale['items']:
					data_date = item['date'] if data_date is not None else data_date
					logging.info(item)
					if item['paymentType'] == 'STAFF MEAL':
						staff_meal = float(item['amount'])
						logging.info(f"{store.store_name} Staff Meal: {staff_meal}")

				data_date = datetime.strptime(data_date, "%Y-%m-%d").date()

				try:
					#We are not taking out staff meal from the gross amount anymore.
					total_amount = sale['total_amount'] #- staff_meal

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
					logging.error(f"An error occurred while saving the computed data for this store:: {e}")

				if self.post_to_byd:
					try:
						if store.post_sale_to_byd:
							'''
								This is the main purpose of this program.
							'''
							logging.info("Sending to ByD.")

							non_zero_values = {key: value for key, value in computed_sales_data.items() if value > 0.00}
							if format_and_post(data_date, store, non_zero_values):
								logging.info("Posting to SAP ByD completed successfully.")
								sales_data.posted_to_byd = True
								sales_data.save()
							else:
								logging.warn("An error may have occurred while posting some entries to SAP ByD, please check your logs for more information.")

							synced_sales.append(sales_data)

						else:
							logging.warn("Posting to ByD for this store was disabled.")

					except Exception as e:
						logging.error(f"Something went wrong while posting to ByD for this store: {e}")

		generate_excel_report(synced_sales, 'Sales_Aggregation_Report')

		logging.info("Completed sync.")