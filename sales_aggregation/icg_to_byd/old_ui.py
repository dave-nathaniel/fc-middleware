import os
from dotenv import load_dotenv
import logging
import tkinter as tk
import tkinter.messagebox
import customtkinter
from datetime import datetime
import subprocess
import time
from PIL import Image


load_dotenv()

customtkinter.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
customtkinter.set_default_color_theme("dark-blue")  # Themes: "blue" (standard), "green", "dark-blue"

script_directory = os.path.dirname(os.path.realpath(__file__))

class CustomFormatter(logging.Formatter):
	def formatTime(self, record, datefmt=None):
		created_time = self.converter(record.created)
		return created_time.strftime("%d-%b-%y %H:%M:%S")


class TextHandler(logging.Handler):
	def __init__(self, text):
		logging.Handler.__init__(self)
		# Store a reference to the Text it will log to
		self.text = text
		self.setFormatter(
			logging.Formatter(f"[%(asctime)s %(levelname)s] -> %(message)s", datefmt='%H:%M:%S')
		)
		self.log_level_colors = {
			"NOTSET": "#000000",
			"DEBUG": "#CCCCCC",
			"INFO": "#1ecbe1",
			"WARN": "#dda322",
			"ERROR": "#FF0000",
			"CRITICAL": "#FF0000",
		}

	def emit(self, record):
		msg = self.format(record)
		msg_level = getattr(record, "levelname")
		def append():
			print(self.log_level_colors[msg_level])
			self.text.configure(state='normal')
			self.text.tag_add(f"tag_{tk.END}", tk.END)
			self.text.tag_config(f"tag_{tk.END}", foreground=self.log_level_colors[msg_level])
			self.text.insert(tk.END, msg + '\n', (f"tag_{tk.END}"))
			self.text.configure(state='disabled')
			# Autoscroll to the bottom
			self.text.yview(tk.END)
		# This is necessary because we can't modify the Text from other threads
		self.text.after(0, append)


class ScrollableFrame(customtkinter.CTkScrollableFrame):
	def __init__(self, master, item_list, command=None, **kwargs):
		super().__init__(master, **kwargs)

		self.items = []
		for i, item in enumerate(item_list):
			self.add_item(item)

	def add_item(self, item):
		new_item = customtkinter.CTkLabel(self, text=item)
		new_item.grid(row=len(self.items), column=0, pady=(0, 10))
		self.items.append(new_item)

		
class App(customtkinter.CTk):
	def __init__(self):
		super().__init__()

		# configure window
		self.title("FC Sales Aggregation")
		self.geometry(f"{1100}x{580}")

		# configure grid layout (4x4)
		self.grid_columnconfigure(1, weight=1)
		self.grid_columnconfigure((2, 3), weight=1)
		self.grid_rowconfigure((0, 1, 2), weight=1)

		# create sidebar frame with widgets
		self.sidebar_frame = customtkinter.CTkFrame(self, width=170, corner_radius=0)
		self.sidebar_frame.grid(row=0, rowspan=4, column=0, padx=(20, 0), pady=(20, 20), sticky="nsew")
		self.sidebar_frame.grid_rowconfigure(4, weight=1)

		self.logo_label = customtkinter.CTkLabel(self.sidebar_frame, text="Sales Aggregation", font=customtkinter.CTkFont(size=16), fg_color="gray30", corner_radius=3)
		self.logo_label.grid(row=0, column=0, pady=(0,20), sticky='ew')

		self.sidebar_button_1 = customtkinter.CTkButton(self.sidebar_frame, text="Lunch Admin", command=self.launch_admin, corner_radius=1)
		self.sidebar_button_1.grid(row=1, column=0, padx=10, pady=10, sticky='n')

		self.sidebar_button_2 = customtkinter.CTkButton(self.sidebar_frame, text="Open Log File", command=self.open_log_file, corner_radius=1)
		self.sidebar_button_2.grid(row=2, rowspan=2, column=0, padx=10, pady=10)

		self.appearance_mode_label = customtkinter.CTkLabel(self.sidebar_frame, text="Appearance Mode:")
		self.appearance_mode_label.grid(row=5, column=0, padx=10, pady=10)
		self.appearance_mode_optionemenu = customtkinter.CTkOptionMenu(self.sidebar_frame, values=["Light", "Dark", "System"],command=self.change_appearance_mode_event)
		self.appearance_mode_optionemenu.grid(row=6, column=0, padx=10, pady=10)

		# create textbox
		self.textbox = customtkinter.CTkTextbox(self, width=250)
		self.textbox.grid(row=0, column=1, columnspan=2, rowspan=3, padx=(20, 0), pady=(20, 0), sticky="nsew")
		self.textbox.configure(state='disabled')

		# create slider and progressbar frame
		self.slider_progressbar_frame = customtkinter.CTkFrame(self, fg_color="transparent")
		self.slider_progressbar_frame.grid(row=3, column=1, columnspan=2, sticky="nsew")
		self.slider_progressbar_frame.grid_columnconfigure(0, weight=1)
		self.slider_progressbar_frame.grid_rowconfigure(4, weight=1)

		self.progressbar_1 = customtkinter.CTkProgressBar(self.slider_progressbar_frame)
		self.progressbar_1.grid(row=0, column=0, columnspan=2, padx=(20, 0), pady=(20, 20), sticky="ew")

		# create scrollable frame
		self.store_update_frame = ScrollableFrame(self, item_list=[], label_text="Processed Stores", label_font=customtkinter.CTkFont(size=14))
		self.store_update_frame.grid(row=0, column=3, padx=15, pady=(20, 0), sticky="nsew")

		self.action_button_frame = customtkinter.CTkFrame(self, fg_color="transparent")
		self.action_button_frame.grid(row=1, column=3, sticky="nsew")
		self.action_button_frame.grid_columnconfigure(3, weight=1)
		self.action_button_frame.grid_rowconfigure(4, weight=1)

		self.action_button = customtkinter.CTkButton(self.action_button_frame, text="Start Sync", command=self.launch_admin, font=customtkinter.CTkFont(size=14, ))
		self.action_button.grid(row=3, column=0, columnspan=2, padx=10, pady=10)

		# set default values
		self.appearance_mode_optionemenu.set("Dark")
		self.progressbar_1.configure(mode="determinnate")
		self.progressbar_1.start()

		self.configure_logging()

	def configure_logging(self, ):
		# Create textLogger
		text_handler = TextHandler(self.textbox)
		# Add the handler to logger
		logger = logging.getLogger()        
		logger.addHandler(text_handler)

		self.update_log_display(f"[{datetime.strftime(datetime.now(), '%d-%b-%y')}] Ready.")

	# Function to update the log display
	def update_log_display(self, message):
		self.textbox.configure(state='normal')
		self.textbox.insert(tk.END, message + '\n')
		self.textbox.see(tk.END)  # Scroll to the end
		self.textbox.configure(state='disabled')

	def change_appearance_mode_event(self, new_appearance_mode: str):
		customtkinter.set_appearance_mode(new_appearance_mode)

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

if __name__ == "__main__":
	app = App()

	app.mainloop()