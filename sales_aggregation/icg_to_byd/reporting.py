import openpyxl
from openpyxl.utils.dataframe import dataframe_to_rows
import pandas as pd
from decimal import Decimal
from datetime import datetime

# Get the current timestamp
current_time = datetime.now()

def generate_excel_report(records, file_path):
	# Format the timestamp with underscores
	formatted_timestamp = current_time.strftime("%Y_%m_%d_%H%M%S")

	# Define headers for the Excel sheet
	headers = ["Date", "Store", "Gross Total", "Net Sales", "VAT", "Consumption Tax", "Tourism Dev. Levy", "Marketing FundProvision", "Locality Marketing Provision", "Mgmt Fee", "Mgmt Fee Share Service", "Mgmt Fee Development", "Mgmt Fee HR", "Rent", "Posted to BYD"]
	
	data = []

	for sale in records:
		data.append([
			sale.date,
			sale.store.store_name,
			sale.gross_total,
			sale.calculated_sales_data.get("net_sales", 0.00),
			sale.calculated_sales_data.get("vat", 0.00),
			sale.calculated_sales_data.get("consumption_tax", 0.00),
			sale.calculated_sales_data.get("tourism_development_levy", 0.00),
			sale.calculated_sales_data.get("marketing_fund_provision", 0.00),
			sale.calculated_sales_data.get("locality_marketing_provision", 0.00),
			sale.calculated_sales_data.get("mgmt_fee", 0.00),
			sale.calculated_sales_data.get("mgmt_fee_share_service", 0.00),
			sale.calculated_sales_data.get("mgmt_fee_development", 0.00),
			sale.calculated_sales_data.get("mgmt_fee_hr", 0.00),
			sale.calculated_sales_data.get("variable_rent", 0.00),
			sale.posted_to_byd,
		])

	df = pd.DataFrame(data, columns=headers)

	# Create a new Excel workbook and add the DataFrame to a new sheet
	wb = openpyxl.Workbook()
	ws = wb.active

	# Add headers
	for col_num, header in enumerate(headers, 1):
		ws.cell(row=1, column=col_num, value=header)

	# Add data
	for r_idx, row in enumerate(data, 2):
		for col_num, value in enumerate(row, 1):
			ws.cell(row=r_idx, column=col_num, value=value)

	# Save the workbook to the specified file path
	wb.save(f"reports/{file_path}_{formatted_timestamp}.xlsx")



if __name__ == '__main__':

	import django
	django.setup()

	from store_services.models import Store, Sales

	generate_excel_report([], 'output')