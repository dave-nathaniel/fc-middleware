from io import BytesIO

import pandas as pd

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Store


User = get_user_model()


class StoreExcelImportExportTests(TestCase):
	def setUp(self):
		# Create superuser for admin login
		self.user = User.objects.create_superuser(username="admin", password="password", email="admin@example.com")
		self.client = Client()
		self.client.login(username="admin", password="password")

		# Initial store record for update tests
		self.initial_store = Store.objects.create(
			store_name="Test Store",
			store_email="initial@example.com",
			icg_warehouse_name="WH 1",
			icg_warehouse_code="WH001",
			byd_cost_center_code="CC001",
		)

		self.upload_url = reverse("admin:store_services_store_upload_excel")
		self.download_url = reverse("admin:store_services_store_download_config")

	def _make_excel_file(self, rows):
		"""Utility to create an in-memory Excel file from list of dict rows."""
		df = pd.DataFrame(rows)
		bio = BytesIO()
		df.to_excel(bio, index=False)
		bio.seek(0)
		return bio

	def test_add_only_does_not_update_existing(self):
		rows = [
			{
				"ICG Current Code": "WH001",
				"ByD Cost Centre Description": "Test Store Updated",
				"Store Email": "updated@example.com",
				"ICG Warehouse Description": "WH 1",
				"ICG Future Code": "",
				"ByD Cost Centre ID": "CC001",
				"ByD SCD Warehouse ID": "",
				"ByD Bill to Party ID": "",
				"ByD Account ID": "",
				"ByD Supplier CK ID": "",
				"ByD Supplier PPU ID": "",
				"VAT": 7.5,
				"Consumption Tax": 0,
				"Tourism Tax": 0,
				"Locality Marketing Provision": 0,
				"Marketing Fund Provision": 0,
				"Management Fee": 0.075,
			},
			{
				"ICG Current Code": "WH002",
				"ByD Cost Centre Description": "New Store",
				"Store Email": "new@example.com",
				"ICG Warehouse Description": "WH 2",
				"ICG Future Code": "",
				"ByD Cost Centre ID": "CC002",
				"ByD SCD Warehouse ID": "",
				"ByD Bill to Party ID": "",
				"ByD Account ID": "",
				"ByD Supplier CK ID": "",
				"ByD Supplier PPU ID": "",
				"VAT": 7.5,
				"Consumption Tax": 0,
				"Tourism Tax": 0,
				"Locality Marketing Provision": 0,
				"Marketing Fund Provision": 0,
				"Management Fee": 0.075,
			},
		]
		bio = self._make_excel_file(rows)

		response = self.client.post(
			self.upload_url,
			{"excel_file": bio, "update_existing": ""},  # update_existing unchecked -> add only
			format="multipart",
		)
		self.assertEqual(response.status_code, 200)
		self.initial_store.refresh_from_db()
		self.assertEqual(self.initial_store.store_email, "initial@example.com")  # unchanged
		self.assertTrue(Store.objects.filter(icg_warehouse_code="WH002").exists())

	def test_update_and_add_updates_existing(self):
		rows = [
			{
				"ICG Current Code": "WH001",
				"ByD Cost Centre Description": "Test Store Updated",
				"Store Email": "updated@example.com",
				"ICG Warehouse Description": "WH 1",
				"ICG Future Code": "",
				"ByD Cost Centre ID": "CC001",
				"ByD SCD Warehouse ID": "",
				"ByD Bill to Party ID": "",
				"ByD Account ID": "",
				"ByD Supplier CK ID": "",
				"ByD Supplier PPU ID": "",
				"VAT": 7.5,
				"Consumption Tax": 0,
				"Tourism Tax": 0,
				"Locality Marketing Provision": 0,
				"Marketing Fund Provision": 0,
				"Management Fee": 0.075,
			},
		]
		bio = self._make_excel_file(rows)

		response = self.client.post(
			self.upload_url,
			{"excel_file": bio, "update_existing": "on"},
			format="multipart",
		)
		self.assertEqual(response.status_code, 200)
		self.initial_store.refresh_from_db()
		self.assertEqual(self.initial_store.store_email, "updated@example.com")

	def test_download_config_returns_excel(self):
		response = self.client.get(self.download_url)
		self.assertEqual(response.status_code, 200)
		self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", response["Content-Type"])
