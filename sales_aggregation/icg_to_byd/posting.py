import os, sys
import logging
from pprint import pprint
from datetime import date
from byd_services.soap import SOAPServices

try:
	ss = SOAPServices()
	ss.connect()
except Exception as e:
	raise e


def post_to_byd(date, items=[]):
	logging.info("Creating Ledger Entry: ")
	logging.info(items)
	req = {
		"ObjectNodeSenderTechnicalID": "T1",
		"CompanyID": "FC-0001",
		"AccountingDocumentTypeCode": "00047",
		"PostingDate": str(date),
		"BusinessTransactionTypeCode": "601",
		"TransactionCurrencyCode": "NGN",
		"Item": items
	}

	response = ss.soap_client.MaintainAsBundle(BasicMessageHeader="", AccountingEntry=req)


def format_and_post(date, store, calculated_sales_data):

	set_amount = ss.client.get_type('{http://sap.com/xi/AP/Common/GDT}Amount')

	def create_posting_data(debit_credit_indicator, profit_centre_id, gl_code, amount):
		return {
			"DebitCreditCode": "1" if debit_credit_indicator.lower() == 'd' else "2",
			"ProfitCentreID": profit_centre_id,
			"ChartOfAccountsItemCode": gl_code,
			'TransactionCurrencyAmount': set_amount(round(amount, 2), currencyCode='NGN'),
		}

	def post_entries(entries):
		for entry in entries:
			logging.debug(entry)
			post_to_byd(date, entries)

	sales_gl = "410001"
	cash_in_transit_gl = "163104"
	vat_gl = "218002"
	consumption_tax_gl = "217018"
	tourism_development_levy_gl = "217016"
	marketing_fund_provision_gl_dr = "612001"
	marketing_fund_provision_gl_cr = "216004"
	locality_marketing_gl = "612003"
	mgmt_fee_gl = "618013"
	rent_gl = "617002"
	accured_expense_gl = "211004"

	ledger_entries = []

	if 'net_sales' in calculated_sales_data:
		logging.info(f"Preparing ledger entry for net_sales")
		net_sales_entries = [
			create_posting_data("d", store.byd_cost_center_code, cash_in_transit_gl, calculated_sales_data['net_sales']),
			create_posting_data("c", "4000000", sales_gl, calculated_sales_data['net_sales']),
		]
		ledger_entries.append(net_sales_entries)

	if 'vat' in calculated_sales_data:
		logging.info(f"Preparing ledger entry for vat")
		vat_entries = [
			create_posting_data("d", "4000000", cash_in_transit_gl, calculated_sales_data['vat']),
			create_posting_data("c", "4000000", vat_gl, calculated_sales_data['vat']),
		]
		ledger_entries.append(vat_entries)

	if 'consumption_tax' in calculated_sales_data:
		logging.info(f"Preparing ledger entry for consumption_tax")
		consumption_tax = [
			create_posting_data("d", "4000000", cash_in_transit_gl, calculated_sales_data['consumption_tax']),
			create_posting_data("c", "4000000", consumption_tax_gl, calculated_sales_data['consumption_tax']),
		]
		ledger_entries.append(consumption_tax)

	if 'tourism_development_levy' in calculated_sales_data:
		logging.info(f"Preparing ledger entry for tourism_development_levy")
		tourism_development_levy = [
			create_posting_data("d", store.byd_cost_center_code, cash_in_transit_gl, calculated_sales_data['tourism_development_levy']),
			create_posting_data("c", "4000000", tourism_development_levy_gl, calculated_sales_data['tourism_development_levy']),
		]
		ledger_entries.append(date, tourism_development_levy)

	if 'marketing_fund_provision' in calculated_sales_data:
		logging.info(f"Preparing ledger entry for marketing_fund_provision")
		marketing_fund_provision = [
			create_posting_data("d", store.byd_cost_center_code, marketing_fund_provision_gl_dr, calculated_sales_data['marketing_fund_provision']),
			create_posting_data("c", "4000000", marketing_fund_provision_gl_cr, calculated_sales_data['marketing_fund_provision']),
		]
		ledger_entries.append(marketing_fund_provision)

	if 'locality_marketing_provision' in calculated_sales_data:
		logging.info(f"Preparing ledger entry for locality_marketing_provision")
		locality_marketing_provision = [
			create_posting_data("d", store.byd_cost_center_code, locality_marketing_gl, calculated_sales_data['locality_marketing_provision']),
			create_posting_data("c", "4000000", marketing_fund_provision_gl_cr, calculated_sales_data['locality_marketing_provision']),
		]
		ledger_entries.append(locality_marketing_provision)

	if 'mgmt_fee' in calculated_sales_data:
		logging.info(f"Preparing ledger entry for mgmt_fee")
		mgmt_fee_entries = [
			create_posting_data("d", store.byd_cost_center_code, mgmt_fee_gl, calculated_sales_data['mgmt_fee']),
			create_posting_data("c", "7000000", mgmt_fee_gl, calculated_sales_data['mgmt_fee_share_service']),
			create_posting_data("c", "6000000", mgmt_fee_gl, calculated_sales_data['mgmt_fee_development']),
			create_posting_data("c", "3000000", mgmt_fee_gl, calculated_sales_data['mgmt_fee_hr']),
		]
		ledger_entries.append(mgmt_fee_entries)

	if 'variable_rent' in calculated_sales_data:
		logging.info(f"Preparing ledger entry for variable_rent")
		variable_rent = [
			create_posting_data("d", store.byd_cost_center_code, rent_gl, calculated_sales_data['variable_rent']),
			create_posting_data("c", "4000000", accured_expense_gl, calculated_sales_data['variable_rent']),
		]
		ledger_entries.append(variable_rent)


	post_entries(ledger_entries)