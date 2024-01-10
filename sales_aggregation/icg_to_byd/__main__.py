import os, sys
from dotenv import load_dotenv
import logging
import json

load_dotenv()

def startup(config_file):
	from .gui import main

	if config_file:
		try:
			with open(config_file, 'r') as f:
				f_content = f.read()
			config = json.loads(f_content)

			main(config)
		except Exception as e:
			logging.error(f"The configuration file {config_file} could not be read: {e}")
	else:
		logging.error(f"Unable to start the process because a configuration file was not supplied.")


if __name__ == '__main__':

	config = sys.argv[1] if (len(sys.argv) > 1) else os.getenv("SALES_AGGREGATION_CONFIG")

	startup(config)

	