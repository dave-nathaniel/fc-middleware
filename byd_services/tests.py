import logging
from django.test import TestCase
from .soap import SOAPServices

# Create your tests here.

try:
	ss = SOAPServices()
	ss.connect()
except Exception as e:
	raise e

def post_to_byd(date, items=[]):

	def equalize_dr_cr(items):
		sum_debit = round(sum(item['TransactionCurrencyAmount']['_value_1'] for item in items if item['DebitCreditCode'] == '1'), 2)
		sum_credit = round(sum(item['TransactionCurrencyAmount']['_value_1'] for item in items if item['DebitCreditCode'] == '2'), 2)

		print(f"Sum of DR side: {sum_debit}")
		print(f"Sum of CR side: {sum_credit}")

		if sum_debit != sum_credit:
			difference = round(sum_debit - sum_credit, 2)
			print(f"DR-CR sides different by {difference}")
			if sum_debit > sum_credit: 
				if difference < 0.05:
					min_credit_value = min((item for item in items if item['DebitCreditCode'] == '2'), key=lambda x: x['TransactionCurrencyAmount']['_value_1'])
					adjusted_value = min_credit_value['TransactionCurrencyAmount']['_value_1'] + difference
					adjusted_value = round(adjusted_value, 2)
					print(f"Adjusting credit value for ProfitCentre '{min_credit_value['ProfitCentreID']}' from <{min_credit_value['TransactionCurrencyAmount']['_value_1']}> to <{adjusted_value}>")
					min_credit_value['TransactionCurrencyAmount']['_value_1'] = adjusted_value
					equalize_dr_cr(items)
				else:
					print(f"A calculation error has occurred: {items}")
					return False
			elif sum_credit > sum_debit:
				difference = difference * -1 #Get the positive value
				if difference < 0.05:
					min_debit_value = min((item for item in items if item['DebitCreditCode'] == '1'), key=lambda x: x['TransactionCurrencyAmount']['_value_1'])
					adjusted_value = min_debit_value['TransactionCurrencyAmount']['_value_1'] + difference
					adjusted_value = round(adjusted_value, 2)
					print(f"Adjusting debit value for ProfitCentre '{min_debit_value['ProfitCentreID']}' from <{min_debit_value['TransactionCurrencyAmount']['_value_1']}> to <{adjusted_value}>")
					min_debit_value['TransactionCurrencyAmount']['_value_1'] = adjusted_value
					equalize_dr_cr(items)
				else:
					print(f"A calculation error has occurred: {items}")
					return False
			else:
					print(f"A calculation error has occurred: {items}")
					return False
		else:
			print("DR-CR sides equal.")

		return items

	if equalize_dr_cr(items):
		print(items)

		req = {
			"ObjectNodeSenderTechnicalID": "T1",
			"CompanyID": "FC-0001",
			"AccountingDocumentTypeCode": "00047",
			"PostingDate": str(date),
			"BusinessTransactionTypeCode": "601",
			"TransactionCurrencyCode": "NGN",
			"Item": items
		}

		print(req)

		try:
			response = ss.soap_client.MaintainAsBundle(BasicMessageHeader="", AccountingEntry=req)

			if response['Log'] is not None:
				print(f"The following issues were raised by SAP ByD: ")
				print(f"{chr(10)}{chr(10).join(['Issue ' + str(counter + 1)  + ': ' + item['Note'] + '.' for counter, item in enumerate(response['Log']['Item'])])}")
				print(f"This entry may have failed to post.")
			else:
				print("Posted successfully.")
				return True

		except Exception as e:
			print(f"The following exception occurred while posting this entry to SAP ByD: {e}")
			print(f"This entry may have failed to post.")

	return False



if __name__ == '__main__':

	items =  [{'DebitCreditCode': '1', 'ProfitCentreID': '4100017-3', 'ChartOfAccountsItemCode': '163104', 'TransactionCurrencyAmount': {
	    '_value_1': 2331550.0,
	    'currencyCode': 'NGN'
	}}, {'DebitCreditCode': '2', 'ProfitCentreID': '4000000', 'ChartOfAccountsItemCode': '410001', 'TransactionCurrencyAmount': {
	    '_value_1': 2072488.89,
	    'currencyCode': 'NGN'
	}}, {'DebitCreditCode': '2', 'ProfitCentreID': '4000000', 'ChartOfAccountsItemCode': '218002', 'TransactionCurrencyAmount': {
	    '_value_1': 155436.67,
	    'currencyCode': 'NGN'
	}}, {'DebitCreditCode': '2', 'ProfitCentreID': '4000000', 'ChartOfAccountsItemCode': '217016', 'TransactionCurrencyAmount': {
	    '_value_1': 103624.44,
	    'currencyCode': 'NGN'
	}}]



	post_to_byd('2024-01-07', items)