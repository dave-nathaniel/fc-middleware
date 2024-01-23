import os, sys
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging
import json

load_dotenv()

def manipulate_date(input_integer):
	# Get the current date
	current_date = datetime.now()
	
	# Check the value of input_integer
	if input_integer == 0:
		result_date = current_date  # If the integer is 0, return the current date
	elif input_integer > 0:
		result_date = current_date + timedelta(days=input_integer)  # Add days to the current date
	else:
		result_date = current_date - timedelta(days=abs(input_integer))  # Subtract days from the current date

	# Return the result in the '%Y-%m-%d' format
	return result_date.strftime('%Y-%m-%d')

def startup(config_file):
	if config_file:
		try:
			with open(config_file, 'r') as f:
				f_content = f.read()
			config = json.loads(f_content)
		except Exception as e:
			logging.error(f"The configuration file {config_file} could not be read: {e}")
			logging.error("<<TERMINATING>>")
			return False

		if config.get("show_ui"):
			from .gui import main
			#Display the UI
			main(config)
		else:
			from .sync import Sync
			#Add a console handler to view logs in the console
			console_handler = logging.StreamHandler(sys.stdout)
			logging.getLogger().addHandler(console_handler)
			logging.getLogger().setLevel(logging.INFO)

			sync = Sync()

			sync.set_save_records(config.get("save_records"))
			sync.set_stores_to_use(config.get("use_only_active_stores"))
			sync.set_post_to_byd(config.get("post_to_byd"))

			if config.get("get_sales_from_icg"):
				#If the app is configured to hide the UI, then set the working date as the date offset defined in the configuration else 
				working_date = manipulate_date(config.get("sales_date_difference"))
				sync.get_sales_from_icg(working_date)
			else:
				file_path = config.get("test_data_file")
				sync.get_sales_from_file(file_path)

			sync.do_sync()
	else:
		logging.error(f"Unable to start the process because a configuration file was not supplied.")


if __name__ == '__main__':

	config = sys.argv[1] if (len(sys.argv) > 1) else os.getenv("SALES_AGGREGATION_CONFIG")

	startup(config)

	