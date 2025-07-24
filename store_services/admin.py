from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.http import HttpResponse, JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django import forms
from django.shortcuts import render
from io import BytesIO
from decimal import Decimal, InvalidOperation
from typing import Union

import pandas as pd


from .models import Store


# -----------------------------------------------------------------------------
# Helper utilities
# -----------------------------------------------------------------------------


EXCEL_COLUMNS = [
	"ICG Current Code",
	"ByD Cost Centre Description",
	"Store Email",
	"ICG Warehouse Description",
	"ICG Future Code",
	"ByD Cost Centre ID",
	"ByD SCD Warehouse ID",
	"ByD Bill to Party ID",
	"ByD Account ID",
	"ByD Supplier CK ID",
	"ByD Supplier PPU ID",
	"VAT",
	"Consumption Tax",
	"Tourism Tax",
	"Locality Marketing Provision",
	"Marketing Fund Provision",
	"Management Fee",
]


# NOTE: Using Union for broader Python version compatibility (<=3.9)
def _decimal_safe(value: Union[str, int, float, None], default: Decimal = Decimal("0")) -> Decimal:
	"""Safely convert a value to Decimal, returning 0 on failure."""
	if value in ("", None):
		return default
	try:
		return Decimal(str(value))
	except (InvalidOperation, ValueError):
		return default


def import_stores_from_excel(file_obj, update_existing: bool = False):
	"""Process an uploaded Excel file and create/update Store records.

	Args:
		file_obj: Uploaded file-like object.
		update_existing: If True, update existing matching records as well.

	Returns:
		Tuple(created_count, updated_count, errors_list)
	"""
	df = pd.read_excel(file_obj, dtype=str)
	# Ensure required columns exist
	missing_cols = [c for c in EXCEL_COLUMNS if c not in df.columns]
	if missing_cols:
		raise ValueError(f"Missing required columns: {', '.join(missing_cols)}")

	# Replace NaN with empty string for safe processing
	df.fillna("", inplace=True)

	created, updated = 0, 0
	errors: list[str] = []

	for idx, row in df.iterrows():
		try:
			warehouse_code = str(row["ICG Current Code"]).strip()
			if not warehouse_code:
				errors.append(f"Row {idx + 2}: Missing ICG Current Code.")  # +2 to account for header + 0-index
				continue

			store_data = {
				"store_name": str(row["ByD Cost Centre Description"]).strip(),
				"store_email": str(row["Store Email"]).strip(),
				"icg_warehouse_name": str(row["ICG Warehouse Description"]).strip(),
				"icg_warehouse_code": warehouse_code,
				"icg_future_warehouse_code": str(row["ICG Future Code"]).strip(),
				"byd_cost_center_code": str(row["ByD Cost Centre ID"]).strip(),
				"byd_sales_unit_id": str(row["ByD SCD Warehouse ID"]).strip(),
				"byd_bill_to_party_id": str(row["ByD Bill to Party ID"]).strip(),
				"byd_account_id": str(row["ByD Account ID"]).strip(),
				"byd_supplier_ck_id": str(row["ByD Supplier CK ID"]).strip(),
				"byd_supplier_ppu_id": str(row["ByD Supplier PPU ID"]).strip(),
				# Numeric fields
				"vat": _decimal_safe(row["VAT"]),
				"consumption_tax": _decimal_safe(row["Consumption Tax"]),
				"tourism_development_levy": _decimal_safe(row["Tourism Tax"]),
				"locality_marketing_provision": _decimal_safe(row["Locality Marketing Provision"]),
				"marketing_fund_provision": _decimal_safe(row["Marketing Fund Provision"]),
				"mgmt_fee": _decimal_safe(row["Management Fee"]),
			}

			store_obj: Store | None = Store.objects.filter(icg_warehouse_code=warehouse_code).first()

			if store_obj is None:
				# Create new store
				Store.objects.create(**store_data)
				created += 1
			else:
				if update_existing:
					for field, value in store_data.items():
						if field == "icg_warehouse_code":
							continue  # Do not allow modifying unique identifier
						setattr(store_obj, field, value)
					store_obj.save()
					updated += 1
				# else: skip updates when update_existing is False
		except Exception as exc:
			errors.append(f"Row {idx + 2}: {exc}")

	return created, updated, errors


# -----------------------------------------------------------------------------
# Custom form for file upload in the admin interface
# -----------------------------------------------------------------------------


class StoreUploadForm(forms.Form):
	excel_file = forms.FileField(label="Excel File (.xlsx)")
	update_existing = forms.BooleanField(
		label="Update Existing Records", required=False, initial=False,
		help_text="Tick to update existing store records as well as add new ones. Leave unticked to add new stores only.",
	)


@staff_member_required
def store_upload_view(request):
	"""Render a simple form for uploading store configuration Excel files."""
	if request.method == "POST":
		form = StoreUploadForm(request.POST, request.FILES)
		if form.is_valid():
			excel = form.cleaned_data["excel_file"]
			update_existing = form.cleaned_data.get("update_existing", False)
			try:
				created, updated, errors = import_stores_from_excel(excel, update_existing=update_existing)
				msg = f"Created: {created}, Updated: {updated}."
				if errors:
					messages.warning(request, f"Store import completed with errors. {msg}")
					return JsonResponse({"success": False, "message": msg, "errors": errors})
				else:
					messages.success(request, f"Store import successful. {msg}")
					return JsonResponse({"success": True, "message": msg})
			except ValueError as ve:
				messages.error(request, str(ve))
				return JsonResponse({"success": False, "errors": [str(ve)]})
	else:
		form = StoreUploadForm()

	return render(request, "admin/store_services/store_upload.html", {"form": form})


@staff_member_required
def download_store_config(request):
	"""Download current store configuration as Excel in the original template format."""
	data = []
	for store in Store.objects.all():
		data.append({
			"ICG Current Code": store.icg_warehouse_code,
			"ByD Cost Centre Description": store.store_name,
			"Store Email": store.store_email,
			"ICG Warehouse Description": store.icg_warehouse_name,
			"ICG Future Code": store.icg_future_warehouse_code,
			"ByD Cost Centre ID": store.byd_cost_center_code,
			"ByD SCD Warehouse ID": store.byd_sales_unit_id,
			"ByD Bill to Party ID": store.byd_bill_to_party_id,
			"ByD Account ID": store.byd_account_id,
			"ByD Supplier CK ID": store.byd_supplier_ck_id,
			"ByD Supplier PPU ID": store.byd_supplier_ppu_id,
			"VAT": store.vat,
			"Consumption Tax": store.consumption_tax,
			"Tourism Tax": store.tourism_development_levy,
			"Locality Marketing Provision": store.locality_marketing_provision,
			"Marketing Fund Provision": store.marketing_fund_provision,
			"Management Fee": store.mgmt_fee,
		})

	df = pd.DataFrame(data, columns=EXCEL_COLUMNS)
	buffer = BytesIO()
	df.to_excel(buffer, index=False)
	buffer.seek(0)

	response = HttpResponse(
		buffer.read(),
		content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	)
	response["Content-Disposition"] = "attachment; filename=store_configuration.xlsx"
	return response


# -----------------------------------------------------------------------------
# Store Admin with custom buttons / links
# -----------------------------------------------------------------------------


class StoreAdmin(admin.ModelAdmin):
	change_list_template = "admin/store_services/store/change_list.html"
	search_fields = [
		"store_name",
		"store_email",
		"byd_account_id",
		"byd_bill_to_party_id",
		"byd_cost_center_code",
		"byd_sales_unit_id",
		"byd_supplier_ck_id",
		"byd_supplier_ppu_id",
		"icg_warehouse_code",
		"icg_warehouse_name",
		"icg_future_warehouse_code",
	]

	readonly_fields = ["last_synced"]

	def get_urls(self):
		urls = super().get_urls()
		info = self.model._meta.app_label, self.model._meta.model_name
		my_urls = [
			path(
				"upload-excel/",
				self.admin_site.admin_view(store_upload_view),
				name="%s_%s_upload_excel" % info,
			),
			path(
				"download-config/",
				self.admin_site.admin_view(download_store_config),
				name="%s_%s_download_config" % info,
			),
		]
		return my_urls + urls

	# Display custom buttons in the change list toolbar (Unfold & Django compatible)
	def changelist_view(self, request, extra_context=None):
		if extra_context is None:
			extra_context = {}
		info = self.model._meta.app_label, self.model._meta.model_name
		upload_url = reverse("admin:%s_%s_upload_excel" % info)
		download_url = reverse("admin:%s_%s_download_config" % info)
		extra_context["extra_buttons"] = format_html(
			'<a class="button" href="{}">Upload Excel</a> <a class="button" href="{}">Download Config</a>',
			upload_url,
			download_url,
		)
		return super().changelist_view(request, extra_context=extra_context)


# Register Store admin
admin.site.register(Store, StoreAdmin)