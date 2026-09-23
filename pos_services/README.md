# POS (Restroworks) integration

This app is the single entry point for the Restroworks POS. It receives what the POS pushes, hands purchase orders to the Store Requisition Portal (SRP) for demand planning, posts stock movements to SAP ByD, and sends the final ByD order back to the POS as an invoice.

```
Restroworks POS ──PO──▶ middleware ──feed──▶ SRP (demand planning) ──▶ ByD sales order / purchase request
       ▲                    ▲  │                        │
       │                    │  └──── link (ByD doc ID) ◀┘
       │   invoice          │
       └──────────────── middleware ◀── poll ── ByD outbound delivery / issued purchase order
Restroworks POS ──GRN / return / wastage──▶ middleware ──Celery──▶ ByD inbound delivery / goods consumption
```

## Endpoints

### Pushed by Restroworks

Authentication is HTTP Basic, using a middleware service user created for Restroworks. Every reply is HTTP 200 with `{"Status": "Success"}`, or with `{"Status": "Fail", "Reason": "..."}` when the push was rejected, which is the format the Restroworks specification asks for. Sending the same document twice is safe: the second push is acknowledged and nothing is created again.

| Method and path | Purpose | Idempotency key |
|---|---|---|
| `POST /api/v1/pos/purchase-orders` | Approved POS purchase order. Replies with `TotalCasesMessage`, the total quantity accepted. | `poId` |
| `POST /api/v1/pos/grns` | GRN (stock entry) against an invoice we sent. | `storeId` + `transactionNumber` |
| `POST /api/v1/pos/vendor-returns` | Return to vendor against a PO. | `storeId` + `returnTransactionNo` |
| `POST /api/v1/pos/wastage` | Wastage, using the schema below. | `storeId` + `wastagePrefix` + `wastageNumber` |

The PO, GRN and vendor return bodies follow the Restroworks "ERP PO Process" document exactly. A GRN is accepted once it is stored, and it is posted to ByD in the background. The ByD result can be seen in the admin (see Reconciliation).

**Wastage schema (defined by us):**

```json
{
  "storeId": "3727",
  "customerKey": "630b9e...",
  "wastagePrefix": "WS",
  "wastageNumber": "41",
  "wastageDate": "2026-09-30T05:00:00Z",
  "tradingDate": "2026-09-29",
  "recordedBy": "store.manager@foodconceptsplc.com",
  "approvedBy": "area.manager@foodconceptsplc.com",
  "items": [
    {
      "itemCode": "RM1000072",
      "itemName": "Chicken, whole",
      "quantity": 1.5,
      "unitCode": "KGM",
      "unitCost": 4200,
      "subTotal": 6300,
      "reasonCode": "EXP",
      "reasonDescription": "Expired",
      "stage": "raw",
      "batches": [{"quantity": 1.5, "expiryDate": "2026-09-29T00:00:00Z", "batchNumber": "L-12"}]
    }
  ]
}
```

These fields are required: `storeId`, `wastageNumber`, `wastageDate`, `recordedBy`, and on each item `itemCode`, `quantity`, `unitCode` (the ByD unit code) and `reasonCode`. `stage` is one of `raw`, `wip` or `finished`.

### Called by the Store Requisition Portal

| Method and path | Purpose |
|---|---|
| `POST /srp-feed/token` | Token endpoint compatible with ICG's `/token` (form fields `grant_type=password`, `username`, `password`). Tokens last 14 days. |
| `GET /srp-feed/api/FoodConcept/StoreRequest/<YYYY-MM-DD>` | POS purchase orders received that day, in the same shape SRP reads from ICG. Lines arrive already approved (`is_declined: false`). |
| `POST /api/v1/pos/purchase-orders/link` | Basic auth (SRP's existing middleware user) or JWT. After SRP syncs an order to ByD, it reports which POS purchase order lines went into which ByD document. |

Link body:

```json
{
  "document_type": "sales_order",
  "document_id": "5001",
  "lines": [{"warehouse": "W101", "series": "BP/O1-19-20/", "orderID": 158, "reference": "10047", "quantity": 10}]
}
```

`document_type` is one of `sales_order`, `purchase_request` or `purchase_order`.

### Called on Restroworks

`sync_dispatches` runs every `POS_DISPATCH_POLL_SECONDS` and sends invoices to `RESTROWORKS_INVOICE_URL?customer_key=<outlet key>`:

- **Warehouse, CK or PPU (sales order):** one invoice per ByD outbound delivery, carrying the quantities actually shipped. The invoice number is `<delivery ID>-<poNumber>`. When one sales order covers several POS purchase orders, what was shipped is allocated to them in PO order.
- **Direct vendor (purchase order):** one invoice once the ByD PO is issued (status 6 or 9), carrying the final quantities and prices. The invoice number is `PO<ByD PO ID>-<poNumber>`.

## How each document posts to ByD

| POS document | ByD posting | Source of the pattern |
|---|---|---|
| GRN, direct vendor | Inbound delivery referenced to the ByD PO items, then `PostGoodsReceipt` | fc-vimp eGRN (`create_inbound_delivery_notification_on_byd`) |
| GRN, Warehouse/CK/PPU | Inbound delivery from the ship-from location to the store's cost center, then `PostGoodsReceipt` | fc-vimp `StockTransfer` branch (`post_goods_receipt_on_byd`) |
| Return to vendor | The same inbound delivery with negative quantities | fc-vimp GRN nullification |
| Wastage | `DoGoodsConsumptionForCostCenter` on the store's cost center | fc-vimp inventory tools bulk consumption |

Each ByD document ID comes from our record: `RWG<id>` for GRNs, `RWR<id>` for returns and `RWW<id>` for wastage. When a task is retried, it looks that ID up first. If the inbound delivery already exists, it resumes from there instead of creating a second one.

## Reconciliation

The admin, under "POS (Restroworks) integration", lists:

- every purchase order, with its ByD documents and the invoices sent back to the POS;
- every GRN, return and wastage record, with its status (Queued, Posted to ByD or Failed), the ByD document ID, the error and the number of attempts. The "Retry posting" action re-queues selected records;
- every invoice, with the Restroworks response. The "Send again" action resends selected invoices.

Failed ByD postings retry automatically `POS_MAX_RETRIES` times. The wait starts at 1 minute and doubles each time, up to a maximum of 30 minutes.

## Configuration

| Variable | Meaning |
|---|---|
| `SAP_URL`, `SAP_USER`, `SAP_PASS` | ByD tenant and OData user (same as fc-vimp) |
| `SAP_COMM_USER`, `SAP_COMM_PASS` | ByD communication user for the goods movement web service (already used by the middleware) |
| `BYD_COMPANY_ID` | Default `FC-0001` |
| `CELERY_BROKER_URL` | Default `redis://127.0.0.1:6379/0` |
| `POS_INTERNAL_VENDOR_CODES` | Comma-separated POS vendor codes of the Warehouse, CK and PPU |
| `RESTROWORKS_INVOICE_URL` | Restroworks `save_purchase_order_invoice` URL, without the query string |
| `RESTROWORKS_AUTHORIZATION` | Full `Authorization` header value Restroworks issues, e.g. `Basic ...` |
| `POS_DISPATCH_POLL_SECONDS` | Default 900 |
| `POS_MAX_RETRIES` | Default 6 |
| `POS_BUSINESS_TIMEZONE` | Default `Africa/Lagos`. Decides which day a PO appears on in the SRP feed |

Each store needs its Restroworks `storeId` entered in **Store → Pos store id** (Django admin).

## Running

```bash
python manage.py migrate
celery -A middleware worker -l info           # on Windows for development: add --pool=solo
celery -A middleware beat -l info
CELERY_TASK_ALWAYS_EAGER=True BYD_POST_DELAY_SECONDS=0 python manage.py test pos_services
```

## SRP changes

- **Settings only:**
  - set `YANOT_BASE_URL` to `https://<middleware host>/srp-feed`, with no trailing slash;
  - set `ICG_USERNAME` / `ICG_PASSWORD` to a middleware service user;
  - set `WAREHOUSE`, `PPU` and `CK` to the POS vendor codes of those locations;
  - set each `Vendor.icg_code` to the vendor's POS code.
- **Code:** `srp_link_back.patch` (in this folder, apply at the SRP repo root with `git apply`) adds one Celery task that calls `/api/v1/pos/purchase-orders/link` after each successful sync, and a `MIDDLEWARE_BASE_URL` setting.

## Open points to confirm

1. **Purchase request to purchase order.**
   - For direct vendors, SRP creates a ByD purchase request, and procurement converts it into a PO.
   - Until we know how to read that PR-to-PO link from ByD, the ByD PO ID has to be added against the POS PO in the admin (the "ByD documents" inline). Only then can the invoice be sent.
2. **Prices on warehouse invoices.** These are sent as 0 for now, because the sales order and outbound delivery reads don't expose a price. Material valuation (as in fc-vimp `get_material_valuation`) could fill them if the POS needs them.
3. **Return to Warehouse/CK/PPU** posts a negative inbound delivery from the supplying location. This needs checking on the ByD test tenant. Restroworks has also not confirmed that `vendor_return` covers internal suppliers.
4. **Wastage reason codes** are stored and reportable in the middleware, but the consumption web service has no reason field. Reason-level reporting inside ByD would need a GL or cost-center mapping per reason code.
5. **Quantity changes by demand planners.** Restroworks cannot amend a PO. The invoice always carries what ByD actually ordered or shipped. The store receives against that, and anything outstanding needs a new PO.
6. **Stock on hand.** SRP's `fetch_current_store_stock` reads ICG. There is no Restroworks equivalent yet.
