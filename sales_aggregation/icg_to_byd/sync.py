import django
import os, sys
import logging
import time
import json
from datetime import date, datetime
from django.utils import timezone
from icg_services.sales_data import ICGSalesData
from .posting import format_and_post

django.setup()

from store_services.models import Store
from sales_aggregation.models import Sale
from .reporting import generate_excel_report, send_email_report


class Sync:

	icg_sales = ICGSalesData()

	def __init__(self, date=None):
		self.data = []
		self.save_records = False
		self.post_to_byd = False
		self.active_stores_only = True
		self.stores_to_use = None
		self.working_date = datetime.now()
		# Set the stores to use based on the active_stores_only flag
		self.set_stores_to_use()

	def set_save_records(self, save_records):
		self.save_records = save_records

	def set_working_date(self, date):
		date = date or self.working_date
		formatted_date = (
			datetime.strptime(date, "%Y-%m-%d").date() if isinstance(date, str) else date.date()
		)
		self.working_date = formatted_date

	def set_post_to_byd(self, post_to_byd):
		self.post_to_byd = post_to_byd

	def set_active_stores_only(self, active_stores_only=None):
		self.active_stores_only = active_stores_only or self.active_stores_only
		
	def set_stores_to_use(self, ):
		self.stores_to_use = Store.objects.filter(post_sale_to_byd=True) if self.active_stores_only else Store.objects.all()

	def set_sales_records(self, records):
		self.data = records

	def get_sales_from_icg(self, date=None):
		'''This method is not in use anymore because we aren't using sales directly from ICG anymore'''
		logging.info(f"Using sales records from ICG.")
		self.set_working_date(date)
		self.set_sales_records(self.icg_sales.get_sales(date)) #YYYY-MM-DD
	
	def get_sales_from_sales_queue(self, ):
		'''
			Fetch sales records from the sales queue.
		'''
		logging.info(f"Fetching sales records from the sales queue.")
		sales = Sale.objects.filter(posted_to_byd=False)
		if self.active_stores_only:
			sales = sales.filter(store__post_sale_to_byd=True)
		# Set only sales with valid signatures and data integrity intact
		sales = [sale for sale in sales if sale.signature_valid() and sale.data_valid()]
		self.set_sales_records(sales)

	def get_sales_from_file(self, path):
		logging.info(f"Using sales records from data file: {path}")
		try:
			with open(path, 'r') as data:
				sales_data = data.read()
			self.set_sales_records(json.loads(sales_data))
			# We should never post sales from a file to ByD
			self.post_to_byd = False
		except Exception as e:
			logging.error(f"An error occurred while reading the data file: {e}")

	def do_sync(self,):
		'''
			This method does the actual process of syncing sales data (i.e. from ICG, sales queue, or file) to ByD.
		'''
		# Path to the generated Excel report if any.
		excel_report = None
		# Sales that were successfully posted to ByD.
		synced_sales = []
		# Sales that could not be posted to ByD.
		posting_errors = []
		#Aactive stores that have no sales data for the current session.
		missing_sales = [store for store in self.stores_to_use if store not in [sale.store for sale in self.data]]
		# The stores which sales should be posted to ByD.
		stores_to_use = self.stores_to_use
		# The sales data to be processed.
		sales = self.data
		
		if sales:
			logging.info(f"{len(stores_to_use)} stores selected for synchronization.")
			# Iterate over each store.
			for sale in sales:
				# The store to which this sale belongs.
				store = sale.store
				# The date of the sale.
				sale_date = sale.sale_date.strftime("%Y-%m-%d")
				# The gross sale amount which has been reconciled.
				total_amount = sale.reconciled_gross_total
				
				logging.info(f"\n{'*' * 20} \nStore: {store.store_name} ({store.icg_warehouse_code}) on {sale_date} \nGross Total: {total_amount} \n{'*' * 20}")
				
				# Post to SAP ByD if the flag is set.
				if self.post_to_byd:
					try:
						logging.info("Sending to ByD.")
						# Extracting computed sales data from the sale object. This is a dictionary containing the calculated sales data for the store.
						computed_sales_data = sale.calculated_sales_data
						# Extracting non-zero values from computed sales data. This is to avoid unnecessary operations in ByD
						non_zero_values = {key: value for key, value in computed_sales_data.items() if value > 0.00}
						# Format and post the sales data to SAP ByD.
						if format_and_post(sale_date, store, non_zero_values, gross_total=total_amount):
							# Posting to SAP ByD completed successfully.
							logging.info("Posting to SAP ByD completed successfully.")
							# Mark the sale as posted to ByD.
							sale.mark_as_posted()
							# Update the last synced date for the store.
							store.last_synced = sale_date
							store.save()
							# Appending the sale to the list of synced sales.
							synced_sales.append(sale)
						else:
							# If posting to SAP ByD failed, adding the store to the list of posting errors.
							posting_errors.append(sale)
							logging.warn(f"Something went wrong while posting some journal entries for {store.store_name} to ByD. More information on this error can be found in the process logs.")
					except Exception as e:
						# If an error occurred while posting to SAP ByD, adding the sale to the list of posting errors.
						posting_errors.append(sale)
						logging.error(f"Something went wrong while posting sale for {store.store_name} on {sale_date} to ByD: {e}")
						
			# Logging the summary of the synchronization process.
			logging.info(f"{len(synced_sales)} sales posted successfully.") if synced_sales else None
			logging.error(f"No sales data for {len(missing_sales)} active stores") if missing_sales else None
			logging.info(f"{(len(synced_sales)*100)/len(stores_to_use)}% of stores were posted to ByD.")
			# Generate an Excel report if sales were successfully posted to ByD.
			excel_report = generate_excel_report(synced_sales, 'Sales_Aggregation_Report') if synced_sales else None
		else:
			logging.error(f"The data source returned no sales. More information on this can be found in the process logs.")
		# Send an email report containing the synchronization summary.
		send_email_report(excel_report, active_stores=stores_to_use, synced_sales=synced_sales, missing_sales=missing_sales, posting_errors=posting_errors)
		# Sync completed.
		logging.info("Completed sync.\n\n")
		return True



if __name__ == '__main__':

	console_handler = logging.StreamHandler(sys.stdout)
	logging.getLogger().addHandler(console_handler)
	logging.getLogger().setLevel(logging.INFO)

	s = Sync()
	# s.get_sales_from_file("sales_aggregation/icg_to_byd/data.json")
	# s.set_post_to_byd(True)
	# s.do_sync()