import os, sys
import logging
from pprint import pprint
from byd_services.soap import SOAPServices

try:
	ss = SOAPServices()
	ss.connect()
except Exception as e:
	raise e


def post_to_byd(date, items=[]):

	def equalize_dr_cr(items):
		sum_debit = round(sum(item['TransactionCurrencyAmount']['_value_1'] for item in items if item['DebitCreditCode'] == '1'), 2)
		sum_credit = round(sum(item['TransactionCurrencyAmount']['_value_1'] for item in items if item['DebitCreditCode'] == '2'), 2)

		logging.info(f"Sum of DR side: {sum_debit}")
		logging.info(f"Sum of CR side: {sum_credit}")

		if sum_debit != sum_credit:
			difference = round(sum_debit - sum_credit, 2)
			logging.warn(f"DR-CR sides different by {difference}")
			if sum_debit > sum_credit: 
				if difference < 0.05:
					min_credit_value = min((item for item in items if item['DebitCreditCode'] == '2'), key=lambda x: x['TransactionCurrencyAmount']['_value_1'])
					adjusted_value = min_credit_value['TransactionCurrencyAmount']['_value_1'] + difference
					adjusted_value = round(adjusted_value, 2)
					logging.info(f"Adjusting credit value for ProfitCentre '{min_credit_value['ProfitCentreID']}' from <{min_credit_value['TransactionCurrencyAmount']['_value_1']}> to <{adjusted_value}>")
					min_credit_value['TransactionCurrencyAmount']['_value_1'] = adjusted_value
					equalize_dr_cr(items)
				else:
					logging.error(f"A calculation error has occurred: {items}")
					return False
			elif sum_credit > sum_debit:
				difference = difference * -1 #Get the positive value
				if difference < 0.05:
					min_debit_value = min((item for item in items if item['DebitCreditCode'] == '1'), key=lambda x: x['TransactionCurrencyAmount']['_value_1'])
					adjusted_value = min_debit_value['TransactionCurrencyAmount']['_value_1'] + difference
					adjusted_value = round(adjusted_value, 2)
					logging.info(f"Adjusting debit value for ProfitCentre '{min_debit_value['ProfitCentreID']}' from <{min_debit_value['TransactionCurrencyAmount']['_value_1']}> to <{adjusted_value}>")
					min_debit_value['TransactionCurrencyAmount']['_value_1'] = adjusted_value
					equalize_dr_cr(items)
				else:
					logging.error(f"A calculation error has occurred: {items}")
					return False
			else:
					logging.error(f"A calculation error has occurred: {items}")
					return False
		else:
			logging.info("DR-CR sides equal.")

		return items

	if equalize_dr_cr(items):
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

		logging.debug(req)

		try:
			response = ss.soap_client.MaintainAsBundle(BasicMessageHeader="", AccountingEntry=req)

			if response['Log'] is not None:
				logging.error(f"The following issues were raised by SAP ByD: ")
				logging.error(f"{chr(10)}{chr(10).join(['Issue ' + str(counter + 1)  + ': ' + item['Note'] + '.' for counter, item in enumerate(response['Log']['Item'])])}")
				logging.error(f"This entry may have failed to post.")
			else:
				return True

		except Exception as e:
			logging.error(f"The following exception occurred while posting this entry to SAP ByD: {e}")
			logging.error(f"This entry may have failed to post.")

	return False


def format_and_post(date, store, calculated_sales_data, **kwargs):

	def create_posting_data(debit_credit_indicator, profit_centre_id, gl_code, amount):
		return {
			"DebitCreditCode": "1" if debit_credit_indicator.lower() == 'd' else "2",
			"ProfitCentreID": profit_centre_id,
			"ChartOfAccountsItemCode": gl_code,
			'TransactionCurrencyAmount': set_amount(round(amount, 2), currencyCode='NGN'),
		}

	def post_entries(entries):
		sucessful = True
		for entry in entries:
			logging.debug(entry)
			if not post_to_byd(date, entry):
				sucessful = False
		return sucessful

	set_amount = ss.client.get_type('{http://sap.com/xi/AP/Common/GDT}Amount')

	gross_total = kwargs.get("gross_total")

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
	
	logging.info(f"Preparing ledger entry for Sales and Taxes")
	if gross_total:
		sales_entries = [
			create_posting_data("d", store.byd_cost_center_code, cash_in_transit_gl, gross_total),
			create_posting_data("c", "4000000", sales_gl, calculated_sales_data['net_sales']),
		]

		sales_entries.append(create_posting_data("c", "4000000", vat_gl, calculated_sales_data['vat'])) if 'vat' in calculated_sales_data else None
		sales_entries.append(create_posting_data("c", "4000000", consumption_tax_gl, calculated_sales_data['consumption_tax'])) if 'consumption_tax' in calculated_sales_data else None
		sales_entries.append(create_posting_data("c", "4000000", tourism_development_levy_gl, calculated_sales_data['tourism_development_levy'])) if 'tourism_development_levy' in calculated_sales_data else None

		ledger_entries.append(sales_entries)

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


	return post_entries(ledger_entries)