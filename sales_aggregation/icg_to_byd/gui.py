import os, sys
from dotenv import load_dotenv
import logging
from datetime import datetime
import subprocess
import time
from .ui.ui_sales_aggregation import Ui_MainWindow
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from .sync import Sync
try:
	from tkinter import filedialog
except Exception as e:
	logging.warn(f"Unable to load tkinter: {e}")

load_dotenv()

class CustomFormatter(logging.Formatter):
	def formatTime(self, record, datefmt=None):
		created_time = self.converter(record.created)
		return created_time.strftime("%d-%b-%y %H:%M:%S")


class TextHandler(logging.Handler):
	def __init__(self, log_method):
		logging.Handler.__init__(self)
		# Store a reference to the Text it will log to
		self.log_method = log_method
		self.setFormatter(
			logging.Formatter(f"[%(asctime)s %(levelname)s] -> %(message)s", datefmt='%H:%M:%S')
		)
		self.log_level_colors = {
			"NOTSET": "#000000",
			"DEBUG": "#CCCCCC",
			"INFO": "#1ecbe1",
			"WARNING": "#dda322",
			"ERROR": "#FF0000",
			"CRITICAL": "#FF0000",
		}

	def emit(self, record):
		msg = self.format(record)
		msg_level = getattr(record, "levelname")
		level_color = self.log_level_colors[msg_level]
		self.log_method(msg, level_color)

		
class Application(Ui_MainWindow):
	def __init__(self, MainWindow, **kwargs):
		super().__init__(MainWindow)

		self.app_config = kwargs.get('config')

		self.configure_logging()
		self.configure_sync()

		self.pushButton.clicked.connect(self.launch_admin)
		self.pushButton_2.clicked.connect(self.open_log_file)
		self.pushButton_8.clicked.connect(self.execute_sync)

	def configure_logging(self, ):
		# Create textLogger
		text_handler = TextHandler(self.update_log_display)
		# Add the handler to logger
		logger = logging.getLogger()        
		logger.addHandler(text_handler)
		self.update_log_display(f"[{datetime.strftime(datetime.now(), '%d-%b-%y')}] Ready.")

	def configure_sync(self, ):
		self.cb_get_sales_from_icg.setChecked(self.app_config.get('get_sales_from_icg', True)) #Get sales from ICG or use data from a file?
		self.cb_use_only_active_stores.setChecked(self.app_config.get('use_only_active_stores', True)) #Use only active stores?
		self.cb_save_records.setChecked(self.app_config.get('save_records', False)) #Save records to database?
		self.cb_post_to_byd.setChecked(self.app_config.get('post_to_byd', False)) #Post journal entries to ByD?
		self.cb_use_todays_date.setChecked(self.app_config.get('sales_date_difference') == 0) #Use todays date?

	def update_log_display(self, message, text_color="#FFFFFF"):
		self.plainTextEdit.setTextColor(text_color)
		self.plainTextEdit.insertPlainText(message + '\n')
		QApplication.processEvents()
		self.plainTextEdit.moveCursor(QTextCursor.End)

	def launch_admin(self, ):
		admin_url = f"{os.getenv('HOST')}:{os.getenv('PORT')}/admin/"
		logging.info(f"Opening {admin_url}")
		try:
			cmd_command = f'start "" "{admin_url}"'
			subprocess.run(cmd_command, shell=True, check=True)

		except subprocess.CalledProcessError as e:
			# Handle errors if the command fails
			logging.error(f"{e.stderr}")

	def open_log_file(self, ):
		# Get the root logger
		logger = logging.getLogger()

		# Check if there is a FileHandler in the handlers list
		file_handler = next((handler for handler in logger.handlers if isinstance(handler, logging.FileHandler)), None)

		if file_handler:
			# Access the file path from the FileHandler
			file_path = file_handler.baseFilename
			logging.info(f"Opening log file: {file_path}")
			time.sleep(1)
			try:
				subprocess.run(f"notepad.exe {file_path}", shell=True, check=True)
			except subprocess.CalledProcessError as e:
				# Handle errors if the command fails
				logging.error(f"{e.stderr}")
		else:
			logging.error("No FileHandler found in the logger handlers.")

	def execute_sync(self, ):
		sync = Sync()

		sync.set_save_records(self.cb_save_records.isChecked())
		sync.set_stores_to_use(self.cb_use_only_active_stores.isChecked())
		sync.set_post_to_byd(self.cb_post_to_byd.isChecked())

		if self.cb_get_sales_from_icg.isChecked():
			if self.cb_use_todays_date.isChecked():
				sync.get_sales_from_icg()
			else:
				#pick the date set in the UI's date input.
				working_date = self.dateEdit.date().toPython()
				sync.get_sales_from_icg(working_date)
		else:
			try:
				file_path = filedialog.askopenfilename(title="Select a file")
				sync.get_sales_from_file(file_path)
			except Exception as e:
				logging.warn(f"Unable to load filedialog: {e}")

		sync.do_sync()


def main(config):
	ui = QApplication(sys.argv)
	MainWindow = QMainWindow()
	app = Application(MainWindow, config=config)
	MainWindow.show()
	sys.exit(ui.exec_())


# if __name__ == "__main__":
# 	main()