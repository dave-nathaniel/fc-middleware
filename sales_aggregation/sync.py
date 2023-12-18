import django
import os, sys
import logging
from pprint import pprint
from datetime import date
from byd_services.soap import SOAPServices
from icg_services.sales_data import ICGSalesData
from django.core.wsgi import get_wsgi_application
from django.db import IntegrityError

django.setup()

from store_services.models import Store, Sales

# Configure logging
log_file_path = 'program_logs.log'
logging.basicConfig(
	filename=log_file_path,
	level=logging.INFO,
	format='%(asctime)s - %(levelname)s - %(message)s',
)

def post_to_byd(date, items=[]):
	print(f"Creating Ledger Entry...")
	ss = SOAPServices()
	ss.connect()

	req = {
		"ObjectNodeSenderTechnicalID": "T1",
		"CompanyID": "FC-0001",
		"AccountingDocumentTypeCode": "00047",
		"PostingDate": f"{date}",
		"BusinessTransactionTypeCode": "601",
		"TransactionCurrencyCode": "NGN",
		"Item": items
	}

	response = ss.soap_client.MaintainAsBundle(BasicMessageHeader="", AccountingEntry=req)

	logging.info("\n")


def make_postings(date, store, calculated_sales_data):
	#1 is debit
	#2 is credit
	ss = SOAPServices()
	ss.connect()
	set_amount = ss.client.get_type('{http://sap.com/xi/AP/Common/GDT}Amount')

	if calculated_sales_data['net_sales'] > 0:
		amount = round(calculated_sales_data['net_sales'], 2)
		amount = set_amount(amount, currencyCode='NGN')

		cash_in_transit_gl = "163104"
		sales_gl = "410001"

		net_sales = [
			{
				"DebitCreditCode": "1",
				"ProfitCentreID": store.byd_cost_center_code,
				"ChartOfAccountsItemCode": cash_in_transit_gl,
				'TransactionCurrencyAmount': amount,
			},
			{
				"DebitCreditCode": "2",
				"ProfitCentreID": "4000000",
				"ChartOfAccountsItemCode": sales_gl,
				'TransactionCurrencyAmount': amount,
			},
		]

		post_to_byd(date, net_sales)

	if calculated_sales_data['vat'] > 0:
		amount = round(calculated_sales_data['vat'], 2)
		amount = set_amount(amount, currencyCode='NGN')

		cash_in_transit_gl = "163104"
		vat_gl = "218002"

		vat = [
			{
				"DebitCreditCode": "1",
				"ProfitCentreID": "4000000",
				"ChartOfAccountsItemCode": cash_in_transit_gl,
				'TransactionCurrencyAmount': amount,
			},
			{
				"DebitCreditCode": "2",
				"ProfitCentreID": "4000000",
				"ChartOfAccountsItemCode": vat_gl,
				'TransactionCurrencyAmount': amount,
			},
		]

		post_to_byd(date, vat)

	if calculated_sales_data['consumption_tax'] > 0:
		amount = round(calculated_sales_data['consumption_tax'], 2)
		amount = set_amount(amount, currencyCode='NGN')

		cash_in_transit_gl = "163104"
		consumption_tax_gl = "217018"

		consumption_tax = [
			{
				"DebitCreditCode": "1",
				"ProfitCentreID": "4000000",
				"ChartOfAccountsItemCode": cash_in_transit_gl,
				'TransactionCurrencyAmount': amount,
			},
			{
				"DebitCreditCode": "2",
				"ProfitCentreID": "4000000",
				"ChartOfAccountsItemCode": consumption_tax_gl,
				'TransactionCurrencyAmount': amount,
			},
		]

		post_to_byd(date, consumption_tax)

	if calculated_sales_data['tourism_development_levy'] > 0:
		amount = round(calculated_sales_data['tourism_development_levy'], 2)
		amount = set_amount(amount, currencyCode='NGN')

		cash_in_transit_gl = "163104"
		tourism_development_levy_gl = "217016"

		tourism_development_levy = [
			{
				"DebitCreditCode": "1",
				"ProfitCentreID": store.byd_cost_center_code,
				"ChartOfAccountsItemCode": cash_in_transit_gl,
				'TransactionCurrencyAmount': amount,
			},
			{
				"DebitCreditCode": "2",
				"ProfitCentreID": "4000000",
				"ChartOfAccountsItemCode": tourism_development_levy_gl,
				'TransactionCurrencyAmount': amount,
			},
		]

		post_to_byd(date, tourism_development_levy)

	if calculated_sales_data['marketing_fund_provision'] > 0:
		amount = round(calculated_sales_data['marketing_fund_provision'], 2)
		amount = set_amount(amount, currencyCode='NGN')

		marketing_fund_provision_gl_dr = "612001"
		marketing_fund_provision_gl_cr = "216004"

		marketing_fund_provision = [
			{
				"DebitCreditCode": "1",
				"ProfitCentreID": store.byd_cost_center_code,
				"ChartOfAccountsItemCode": marketing_fund_provision_gl_dr,
				'TransactionCurrencyAmount': amount,
			},
			{
				"DebitCreditCode": "2",
				"ProfitCentreID": "4000000",
				"ChartOfAccountsItemCode": marketing_fund_provision_gl_cr,
				'TransactionCurrencyAmount': amount,
			},
		]

		post_to_byd(date, marketing_fund_provision)

	if calculated_sales_data['locality_marketing_provision'] > 0:
		amount = round(calculated_sales_data['locality_marketing_provision'], 2)
		amount = set_amount(amount, currencyCode='NGN')

		locality_marketing_gl = "612003"
		marketing_fund_provision_gl_cr = "216004"

		locality_marketing_provision = [
			{
				"DebitCreditCode": "1",
				"ProfitCentreID": store.byd_cost_center_code,
				"ChartOfAccountsItemCode": locality_marketing_gl,
				'TransactionCurrencyAmount': amount,
			},
			{
				"DebitCreditCode": "2",
				"ProfitCentreID": "4000000",
				"ChartOfAccountsItemCode": marketing_fund_provision_gl_cr,
				'TransactionCurrencyAmount': amount,
			},
		]

		post_to_byd(date, locality_marketing_provision)

	if calculated_sales_data['mgmt_fee'] > 0:

		mgmt_fee = set_amount(round(calculated_sales_data['mgmt_fee'], 2), currencyCode='NGN')
		mgmt_fee_share_service = set_amount(round(calculated_sales_data['mgmt_fee_share_service'], 2), currencyCode='NGN')
		mgmt_fee_development = set_amount(round(calculated_sales_data['mgmt_fee_development'], 2), currencyCode='NGN')
		mgmt_fee_hr = set_amount(round(calculated_sales_data['mgmt_fee_hr'], 2), currencyCode='NGN')

		mgmt_fee_gl = "618013"

		mgmt_fee_data = [
			{
				"DebitCreditCode": "1",
				"ProfitCentreID": store.byd_cost_center_code,
				"ChartOfAccountsItemCode": mgmt_fee_gl,
				'TransactionCurrencyAmount': mgmt_fee,
			},
			{
				"DebitCreditCode": "2",
				"ProfitCentreID": "7000000",
				"ChartOfAccountsItemCode": mgmt_fee_gl,
				'TransactionCurrencyAmount': mgmt_fee_share_service,
			},
			{
				"DebitCreditCode": "2",
				"ProfitCentreID": "6000000",
				"ChartOfAccountsItemCode": mgmt_fee_gl,
				'TransactionCurrencyAmount': mgmt_fee_development,
			},
			{
				"DebitCreditCode": "2",
				"ProfitCentreID": "3000000",
				"ChartOfAccountsItemCode": mgmt_fee_gl,
				'TransactionCurrencyAmount': mgmt_fee_hr,
			},
		]

		post_to_byd(date, mgmt_fee_data)

	if calculated_sales_data['variable_rent'] > 0:
		amount = round(calculated_sales_data['variable_rent'], 2)
		amount = set_amount(amount, currencyCode='NGN')

		rent_gl = "617002"
		accured_expense_gl = "211004"

		variable_rent = [
			{
				"DebitCreditCode": "1",
				"ProfitCentreID": store.byd_cost_center_code,
				"ChartOfAccountsItemCode": rent_gl,
				'TransactionCurrencyAmount': amount,
			},
			{
				"DebitCreditCode": "2",
				"ProfitCentreID": "4000000",
				"ChartOfAccountsItemCode": accured_expense_gl,
				'TransactionCurrencyAmount': amount,
			},
		]

		post_to_byd(date, variable_rent)




def do_sync():
	icg_sales = ICGSalesData()
	data = icg_sales.get_sales("2023-12-17")

	# data = [{"warehouseCode": "I0", "warehouseName": "LAG, ILUPEJU", "date": "2023-12-14", "paymentType": "CASH", "amount": "211650.00"}, {"warehouseCode": "I0", "warehouseName": "LAG, ILUPEJU", "date": "2023-12-14", "paymentType": "STAFF MEAL", "amount": "42466.00"}, {"warehouseCode": "I0", "warehouseName": "LAG, ILUPEJU", "date": "2023-12-14", "paymentType": "DEBIT CARD", "amount": "1197750.00"}, {"warehouseCode": "I0", "warehouseName": "LAG, ILUPEJU", "date": "2023-12-14", "paymentType": "CREDIT", "amount": "504100.00"}, {"warehouseCode": "I0", "warehouseName": "LAG, ILUPEJU", "date": "2023-12-14", "paymentType": "BANK TRANSFER", "amount": "13000.00"}]

	# data = [{"warehouseCode": "M9", "warehouseName": "CALABAR, NDIDEM", "date": "2023-12-13", "paymentType": "CASH", "amount": "187650"}, {"warehouseCode": "M9", "warehouseName": "CALABAR, NDIDEM", "date": "2023-12-13", "paymentType": "DEBIT CARD", "amount": "956950"}, {"warehouseCode": "M9", "warehouseName": "CALABAR, NDIDEM", "date": "2023-12-13", "paymentType": "BANK TRANSFER", "amount": "5200"}]

	if data:
		grouped_data = icg_sales.group_data_by_warehouse(data)

		# Print the grouped data
		for warehouse, sale in grouped_data.items():

			try:
				store = Store.objects.get(icg_warehouse_code=warehouse)
			except Exception as e:
				logging.error(f"Something went wrong: {e}")
				logging.error(f"Warehouse: {warehouse}")
				continue

			staff_meal = 0.00
			water_sales = 0.00
			data_date = ""

			logging.info(f"Store: {store.store_name}")
			logging.info(f"Initial Total: {sale['total_amount']}")

			for item in sale['items']:
				data_date = item['date'] if data_date is not None else data_date
				if item['paymentType'] == 'STAFF MEAL':
					staff_meal = float(item['amount'])
					logging.info(f"{store.store_name} Staff Meal: {staff_meal}")
					logging.info(f"Total After Staff Meal: {sale['total_amount'] - staff_meal}")
			
			#Staff meal calculation
			total_amount = sale['total_amount'] #- staff_meal

			try:
				sales_instance = Sales(
					store=store,
					sales_data=sale['items'],
					gross_total=total_amount,
					water_sales=water_sales,
					staff_meal=staff_meal,
					date=date.today(),
				)


				sale_data = sales_instance.calculate()
				
				# sales_instance.save()

				# Print the total amount for the warehouse
				logging.info(f"Total Amount: {sale['total_amount']}")
				logging.info(f"Sales data for {store.store_name} inserted successfully.")
			except Exception as e:
				logging.error(f"An error occurred: {e}")
			try:
				if store.post_sale_to_byd:
					logging.info("Sending to ByD.")
					make_postings(data_date, store, sale_data)
				else:
					logging.info("Posting to ByD for this store was disabled.")
			except Exception as e:
				logging.error(f"Something went wrong: {e}")

	print("Completed sync.")


if __name__ == '__main__':
	do_sync()