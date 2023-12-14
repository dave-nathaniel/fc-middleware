import tkinter as tk
from tkinter import filedialog
import logging
from . import sync

# Configure logging
log_file_path = 'program_logs.log'
logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

# Function to be triggered by the button
def trigger_function():
    logging.info("Button clicked! Function triggered.")

# Function to select a file
def select_file():
    file_path = filedialog.askopenfilename(title="Select a file")
    logging.info(f"Selected config file: {file_path}")

# Create the main Tkinter window
root = tk.Tk()
root.title("Simple Tkinter Interface")

# Create and configure the text widget for logging
log_display = tk.Text(root, height=10, width=50)
log_display.pack()

# Function to update the log display
def update_log_display(message):
    log_display.insert(tk.END, message + '\n')
    log_display.see(tk.END)  # Scroll to the end

# Redirect logs to update_log_display function
class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        log_message = self.format(record)
        update_log_display(log_message)

# Create a handler and set the level to INFO
text_handler = TextHandler(log_display)
text_handler.setLevel(logging.INFO)

# Add the handler to the root logger
root_logger = logging.getLogger()
root_logger.addHandler(text_handler)

# Create the button to trigger the function
button_trigger = tk.Button(root, text="Trigger Function", command=trigger_function)
button_trigger.pack()

# Create the button to select a file
button_select_file = tk.Button(root, text="Select File", command=select_file)
button_select_file.pack()

# Run the Tkinter event loop
root.mainloop()