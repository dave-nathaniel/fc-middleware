import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Configure logging with rotating log
log_file_path = f'logs/sales_sync_{datetime.now().strftime("%Y_%m_%d")}.log'
max_log_size = 1 * 1024 * 1024  # 5 MB
backup_count = 10  # Number of backup log files to keep

# Create a rotating file handler
file_handler = RotatingFileHandler(
	log_file_path,
	maxBytes=max_log_size,
	backupCount=backup_count,
)

# Configure the formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Add the rotating file handler to the root logger
logging.getLogger().addHandler(file_handler)

# Set the logging level
logging.getLogger().setLevel(logging.INFO)
