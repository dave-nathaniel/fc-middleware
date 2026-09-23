"""
SAP ByD goods movement (SOAP) client used to post POS stock wastage.

Wastage is posted as a goods consumption for the store's cost center, the same
web service operation fc-vimp uses for its bulk consumption upload
(DoGoodsConsumptionForCostCenter). This reduces stock at the store and expenses
it at weighted average cost.
"""
import os
import logging
from pathlib import Path

from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.transports import Transport

from .rest import ByDError

logger = logging.getLogger(__name__)

WSDL_PATH = Path(__file__).resolve().parent / "wsdl" / "InventoryProcessingGoodsAndActivityConfirmationGoodsMovementIn.wsdl"
BINDING = "{http://sap.com/xi/AP/LogisticsExecution/Global}binding"
SERVICE_PATH = "/sap/bc/srt/scs/sap/inventoryprocessinggoodsandac3"
COMPANY_ID = os.getenv("BYD_COMPANY_ID", "FC-0001")

_service = None
_client = None


def _get_service():
	global _service, _client
	if _service is None:
		session = Session()
		session.auth = HTTPBasicAuth(os.getenv("SAP_COMM_USER"), os.getenv("SAP_COMM_PASS"))
		transport = Transport(
			session=session,
			timeout=int(os.getenv("SAP_TRANSPORT_TIMEOUT", "30")),
			operation_timeout=int(os.getenv("SAP_OPERATION_TIMEOUT", "120")),
		)
		_client = Client(str(WSDL_PATH), transport=transport)
		endpoint = os.getenv("SAP_URL", "").rstrip("/") + SERVICE_PATH
		_service = _client.create_service(BINDING, endpoint)
	return _service, _client


def _raise_on_errors(response):
	log = response["Log"] if response else None
	if not log:
		return
	items = log["Item"] or []
	errors = [item["Note"] for item in items if str(item["SeverityCode"] or "3") == "3"]
	if errors:
		raise ByDError("; ".join(errors))


def post_consumption_for_cost_center(external_id, cost_center_id, items, transaction_datetime):
	"""
		Posts a goods consumption against a store's cost center.
		:param external_id: our unique reference for the document (idempotency key on our side).
		:param cost_center_id: the store's ByD cost center (also used as site and logistics area).
		:param items: [{"line": "1", "product_id": "RM100", "quantity": 2.5, "unit_code": "KGM"}]
		:param transaction_datetime: ISO 8601 date-time of the event.
	"""
	service, client = _get_service()
	quantity_type = client.get_type("{http://sap.com/xi/AP/Common/GDT}Quantity")
	lines = [
		{
			"ExternalItemID": f"{external_id}-{item['line']}",
			"MaterialInternalID": item["product_id"],
			"OwnerPartyInternalID": COMPANY_ID,
			"InventoryRestrictedUseIndicator": "false",
			"LogisticsAreaID": cost_center_id,
			"InventoryItemChangeQuantity": {
				"Quantity": quantity_type(item["quantity"], unitCode=item["unit_code"]),
				"QuantityTypeCode": item["unit_code"],
			},
		}
		for item in items
	]
	request = {
		"ExternalID": external_id,
		"SiteID": cost_center_id,
		"TransactionDateTime": transaction_datetime,
		"InventoryMovementDirectionCode": "1",  # 1 = outbound (stock leaves the store)
		"CostCenterID": cost_center_id,
		"InventoryChangeItemGoodsConsumptionInformationForCostCenter": lines,
	}
	response = service.DoGoodsConsumptionForCostCenter(GoodsAndActivityConfirmation=request)
	_raise_on_errors(response)
	return {"external_id": external_id}
