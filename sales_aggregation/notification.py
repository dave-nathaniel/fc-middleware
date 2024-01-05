import os
from django.core.mail import EmailMessage
from django.core.wsgi import get_wsgi_application
import logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'unionbank.settings')


logging.basicConfig(filename="C:\\web-apis\\logs\\delivery-log.txt", encoding='utf-8', level=logging.DEBUG, format='[%(asctime)s] %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')



class Notification(object):
	"""
		This class handles everything relating to delivering notifications.
		Implemented Notification types:
		1. Email
	"""

	#Must be set when instantiating the class.
	title = ""

	#Must be set when instantiating the class.
	body = ""

	email = {
		'from_email': "ubnexpress1@unionbankng.com",
		'to_email': [],
		'html': True
	}

	notification_type = ""

	def __init__(self, title, body):
		self.title = title
		self.body = body


	def email_notification(self, to, title=None, body=None, html=True, attachments=[]):
		'''
			Prepare an email notification to send.
			to: List of emails to send to.
			title: If title is set, it overrides the title set on instantiating the class.
			body: If body is set, it overrides the body set on instantiating the class.
		'''
		self.email['to_email'] = to
		self.email['html'] = html
		self.title = title if title is not None else self.title
		self.body = body if body is not None else self.body

		self.attachments = attachments

		#Set the notification type
		self.notification_type = 'email'

		return self

	
	def send(self, ):
		'''
			This method sends the notification via the selected  
		'''
		if self.notification_type == 'email':
			return self.send_email()
		else:
			return False


	def send_email(self, ):
		email_from = self.email['from_email']
		email_to = self.email['to_email']
		email_subject = self.title
		email_body = self.body

		content_subtype = 'plain'

		if self.email['html']:
			template_file = f"C:\\web-apis\\api\\templates\\email.html"

			try:
				with open(template_file, 'r', encoding='utf-8') as template:
					content = template.read()
			except FileNotFoundError as e:
				print(f"Template file not found in {template_file}")
				return False


			#Insert the message into the template
			email_body = content.replace("{{__EMAIL_CONTENT__}}", email_body)

			content_subtype = 'html'


		email = EmailMessage(
			subject=email_subject, 
			body=email_body, 
			from_email=email_from, 
			to=email_to
		)

		email.content_subtype = content_subtype

		try:
			#Add the attachments, if any.
			for attachment_path in self.attachments:

				logging.info(f"Adding {attachment_path} as attachment to EMAIL...")

				# get the file name from the path
				file_name = os.path.basename(attachment_path)

				with open(attachment_path, 'rb') as f:
					# add the file as an attachment to the email
					email.attach(file_name, f.read())

			email.send()

			return True

		except Exception as e:
			logging.error(e) 
			return False





# mail = Notification("Your approval is required.", "<h1>Hello</h1><p>Welcome to nothingness</p>")

# mail.email_notification(['dnathaniel@wajesmart.com'], html=False).send()


