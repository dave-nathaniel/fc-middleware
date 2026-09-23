"""
Minimal SAP ByD OData client used by the POS (Restroworks) integration.

Only the calls the integration needs are implemented. They mirror the ones
already proven in production by the VIMP/eGRN code base (fc-vimp byd_service):
inbound delivery + goods receipt, purchase order read, sales order read and
outbound delivery read.

The session (Basic auth + CSRF token) is created lazily on first use so that
importing this module never talks to SAP.
"""
import os
import logging

from requests import Session
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

ODATA_ROOT = "/sap/byd/odata/cust/v1"
# (connect, read) timeouts in seconds for every SAP call.
DEFAULT_TIMEOUT = (15, 120)


class ByDError(Exception):
	"""Raised when ByD rejects a request or returns an unexpected response."""


def _results(node):
	"""ByD returns collections either as a list or as {"results": [...]}."""
	if isinstance(node, dict):
		return node.get("results") or []
	return node or []


class ByDClient:

	def __init__(self):
		self.endpoint = os.getenv("SAP_URL", "").rstrip("/")
		self.auth = HTTPBasicAuth(os.getenv("SAP_USER"), os.getenv("SAP_PASS"))
		self.session = None
		self.csrf_token = None

	# ------------------------------------------------------------------
	# Transport
	# ------------------------------------------------------------------
	def _url(self, path):
		return f"{self.endpoint}{ODATA_ROOT}/{path}"

	def _connect(self):
		self.session = Session()
		response = self.session.get(
			self._url("khpurchaseorder/"),
			auth=self.auth,
			headers={"x-csrf-token": "fetch"},
			timeout=DEFAULT_TIMEOUT,
		)
		if response.status_code != 200:
			raise ByDError(f"Could not open a ByD session (HTTP {response.status_code}).")
		self.csrf_token = response.headers.get("x-csrf-token", "")

	def get(self, path):
		if self.session is None:
			self._connect()
		response = self.session.get(self._url(path), auth=self.auth, timeout=DEFAULT_TIMEOUT)
		if response.status_code != 200:
			raise ByDError(f"GET {path} failed (HTTP {response.status_code}): {response.text[:500]}")
		return response.json().get("d", {}).get("results")

	def post(self, path, payload=None, expected=(200, 201)):
		if self.session is None:
			self._connect()
		headers = {
			"Accept": "application/json",
			"Content-Type": "application/json",
			"x-csrf-token": self.csrf_token,
		}
		response = self.session.post(
			self._url(path), json=payload, auth=self.auth, headers=headers, timeout=DEFAULT_TIMEOUT
		)
		if response.status_code == 403 and "csrf" in response.text.lower():
			# Token expired: open a new session once and retry.
			self._connect()
			headers["x-csrf-token"] = self.csrf_token
			response = self.session.post(
				self._url(path), json=payload, auth=self.auth, headers=headers, timeout=DEFAULT_TIMEOUT
			)
		if response.status_code not in expected:
			raise ByDError(f"POST {path} failed (HTTP {response.status_code}): {response.text[:1000]}")
		return response.json().get("d", {}).get("results") if response.content else {}

	# ------------------------------------------------------------------
	# Purchase orders
	# ------------------------------------------------------------------
	def get_purchase_order(self, po_id):
		"""Returns the ByD PO (with its items) or None."""
		results = self.get(
			f"khpurchaseorder/PurchaseOrderCollection?$format=json&$expand=Supplier,Item"
			f"&$filter=ID eq '{po_id}'"
		)
		results = _results(results)
		if not results:
			return None
		po = results[0]
		po["Item"] = _results(po.get("Item"))
		return po

	# ------------------------------------------------------------------
	# Sales orders / outbound deliveries (Warehouse, CK, PPU supply)
	# ------------------------------------------------------------------
	def get_sales_order(self, so_id):
		results = _results(self.get(
			f"khsalesorder/SalesOrderCollection?$format=json"
			f"&$expand=Item,Item/ItemProduct,Item/ItemShipFromLocation&$filter=ID eq '{so_id}'"
		))
		if not results:
			return None
		so = results[0]
		so["Item"] = _results(so.get("Item"))
		return so

	def get_sales_order_outbound_deliveries(self, so_id):
		"""
			Outbound deliveries created for a sales order, from its DocumentReference
			node (TypeCode 73). ByD ObjectIDs are the UUID without dashes.
		"""
		results = _results(self.get(
			f"khsalesorder/SalesOrderCollection?$format=json&$expand=DocumentReference&$filter=ID eq '{so_id}'"
		))
		if not results:
			return []
		deliveries = []
		for ref in _results(results[0].get("DocumentReference")):
			if str(ref.get("TypeCode")) == "73" and ref.get("UUID"):
				deliveries.append({
					"ID": ref.get("ID"),
					"ObjectID": ref["UUID"].replace("-", "").upper(),
				})
		return deliveries

	def get_outbound_delivery(self, object_id):
		result = self.get(
			f"khoutbounddelivery/OutboundDeliveryCollection('{object_id}')?$format=json"
			f"&$expand=Item,Item/ItemDeliveryQuantity,ShipFromLocation"
		)
		if isinstance(result, list):
			result = result[0] if result else None
		if result:
			result["Item"] = _results(result.get("Item"))
		return result

	# ------------------------------------------------------------------
	# Inbound deliveries (goods receipt at the store)
	# ------------------------------------------------------------------
	def find_inbound_delivery(self, external_id):
		"""Looks up an inbound delivery by the ID we created it with (idempotency)."""
		results = _results(self.get(
			f"khinbounddelivery/InboundDeliveryCollection?$format=json&$filter=ID eq '{external_id}'&$top=1"
		))
		return results[0] if results else None

	def create_inbound_delivery(self, payload):
		return self.post("khinbounddelivery/InboundDeliveryCollection", payload, expected=(201,))

	def post_goods_receipt(self, object_id):
		return self.post(f"khinbounddelivery/PostGoodsReceipt?ObjectID='{object_id}'")
