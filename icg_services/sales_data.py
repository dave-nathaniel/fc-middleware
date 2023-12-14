import os, sys
import requests
from itertools import groupby
from pathlib import Path
from dotenv import load_dotenv
import concurrent.futures
from datetime import date

dotenv_path = os.path.join(Path(__file__).resolve().parent.parent, '.env')
load_dotenv(dotenv_path)

# Get today's date
today_date = date.today()

# Format and display the date
# formatted_date = today_date.strftime('%Y-%m-%d')
formatted_date = "2023-12-13"


def download_in_chunks(url, **kwargs):

	def download_chunk(url, start_byte, end_byte, headers={}):
		h = {"Range": f"bytes={start_byte}-{end_byte}"}
		headers.update(**kwargs)
		response = requests.get(url, headers=headers)
		return response.content

	req = requests.head(url, headers=kwargs)
	# total_bytes = int(req.get('Content-Length', 0))

	print(dir(req))
	print(req.request.headers)
	print(req.request.headers)
	# print(req.response.headers)
	# print(f"Data length: {total_bytes}")
	sys.exit()

	# Number of threads (you can adjust this based on your needs)
	num_threads = 3

	# Calculate the range for each thread
	chunk_size = total_bytes // num_threads
	ranges = [(i * chunk_size, (i + 1) * chunk_size - 1) for i in range(num_threads - 1)]
	ranges.append(((num_threads - 1) * chunk_size, total_bytes - 1))

	with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
		# Use executor.map to apply the function to each range concurrently
		results = list(executor.map(lambda r: download_chunk(url, *r, headers=headers), ranges))

	# Process the results as needed
	full_data = b"".join(results)
	print(f"Total downloaded bytes: {len(full_data)}")
	print(f"{full_data}")

	return full_data


def get_water_sales(warehouse_code, date):
	pass

	
class ICGSalesData:

	BASE_URL = os.getenv("ICG_HOST")
	TOKEN_ENDPOINT = f"{BASE_URL}/token"
	SALES_DATA_ENDPOINT = f"{BASE_URL}/api/FoodConcept/Sales/{formatted_date}"

	def __init__(self, ):
		pass

	def obtain_token(self, config=None):
		'''
			Returns a token obtained from the token endpoint.
			Throws an error if request fails for whatever reason.
		'''

		# Assuming _user, _pass, and _host are defined somewhere in your code
		AUTH_DATA = {
			'grant_type': 'password',
			'username': os.getenv('ICG_USER'),
			'password': os.getenv('ICG_PASSWORD')
		}

		# Headers for the request
		headers = {
			'Content-Type': 'application/x-www-form-urlencoded'
		}

		# Prepare the data for the request body
		payload = '&'.join([f'{key}={value}' for key, value in AUTH_DATA.items()])

		# Make the POST request
		response = requests.post(self.TOKEN_ENDPOINT, headers=headers, data=payload)

		# Check if the request was successful (status code 200)
		if response.status_code == 200:
			# Parse the JSON data from the response
			json_response = response.json()
			
			# Access the 'access_token' and store it in a variable
			auth_user_token = json_response.get('access_token')
			
			# Print or use the token as needed
			return auth_user_token
		else:
			# Print an error message if the request was not successful
			print(f"Error: Unable to fetch token. Status code: {response.status_code}")
			print(response.text)

	def get_today_sales(self, ):
		token = self.obtain_token()
		print(f"Fetching sales data...")
		headers = {
			"Authorization": f"Bearer {token}"
		}

		# Make a request to the endpoint
		response = requests.get(self.SALES_DATA_ENDPOINT, headers=headers)
		
		# Check if the request was successful (status code 200)
		if response:
			# Parse the JSON data from the response
			data = response.json()
			return data
		else:
			# Print an error message if the request was not successful
			print(f"Error: {response}")
			return None

	def group_data_by_warehouse(self, sales_data):
		# Sort the data by "WarehouseName" key
		sorted_data = sorted(sales_data, key=lambda x: x["warehouseCode"])
		
		# Group the sorted data by "WarehouseName"
		grouped_data = {key: list(group) for key, group in groupby(sorted_data, key=lambda x: x["warehouseCode"])}

		# Calculate the total amount for each warehouse
		for warehouse_name, warehouse_data in grouped_data.items():
			total_amount = sum(float(item['amount']) for item in warehouse_data)
			grouped_data[warehouse_name] = {'items': warehouse_data, 'total_amount': total_amount}
		
		return grouped_data