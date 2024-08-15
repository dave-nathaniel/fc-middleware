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

def read_config_file(config_file):
	try:
		# Read the configuration file and load the JSON content
		with open(config_file, 'r') as f:
			f_content = f.read()
		return json.loads(f_content)
	except Exception as e:
		logging.error(f"The configuration file {config_file} could not be read: {e} \n <<TERMINATING>> \n")
	return False

def startup(config):
	# Call up the user interface if enabled in the configuration, else proceed to run the synchronization without the UI
	if config.get("show_ui"):
		from .gui import main
		# Display the UI
		main(config)
	else:
		from .sync import Sync
		# Add a console handler to view logs in the console
		console_handler = logging.StreamHandler(sys.stdout)
		logging.getLogger().addHandler(console_handler)
		logging.getLogger().setLevel(logging.INFO)
		
		# Initialize the Sync object and set the configuration parameters
		sync = Sync()
		# working_date = manipulate_date(config.get("sales_date_difference")) #set the working date as the date offset defined in the configuration
		# Set the flag based on the configuration
		sync.set_active_stores_only(config.get("use_only_active_stores", True))
		sync.set_post_to_byd(config.get("post_to_byd"))
		# Get the sales data based on the configuration
		sync.get_sales_from_file(config.get("test_data_file")) if config.get("use_test_data_file") else sync.get_sales_from_sales_queue()
		# Perform the synchronization and return the result
		sync.do_sync()
	
	return True


if __name__ == '__main__':
	# Get the configuration file path from the command line arguments or environment variable
	config = sys.argv[1] if (len(sys.argv) > 1) else os.getenv("SALES_AGGREGATION_CONFIG")
	# Call the startup function with the configuration file path
	config_file = read_config_file(config)
	if config_file:
		startup(config_file)
	else:
		e = f"Unable to start the process because a configuration file was not supplied."
		logging.error(e)