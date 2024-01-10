import traceback, logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Configure logging with rotating log
log_file_path = f'logs/sales_sync_{datetime.now().strftime("%Y_%m_%d")}.log'
max_log_size = 1048576  # 1 MB
backup_count = 10  # Number of backup log files to keep

file_handler = RotatingFileHandler(
	log_file_path,
	maxBytes=max_log_size,
	backupCount=backup_count
)

# Configure the formatter
log_format = '%(asctime)s - (%(levelname)s): %(message)s'
formatter = logging.Formatter(log_format, datefmt='%d%b%y at %I:%M%p')
file_handler.setFormatter(formatter)

# Add the rotating file handler to the root logger
logging.getLogger().addHandler(file_handler)

# Set the logging level
logging.getLogger().setLevel(logging.INFO)

print(f"Logging to file: {log_file_path}")