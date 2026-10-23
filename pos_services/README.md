# POS (Restroworks) integration

This app is the single entry point for the Restroworks POS. It receives what the POS pushes, hands purchase orders to the Store Requisition Portal (SRP) for demand planning, posts stock movements to SAP ByD, and sends the final ByD order back to the POS as an invoice. It also takes ICG's place as Blue Prism's source of daily sales.

```
Restroworks POS ──PO──▶ middleware ──feed──▶ SRP (demand planning) ──▶ ByD sales order / purchase request
       ▲                    ▲  │                        │
       │                    │  └──── link (ByD doc ID) ◀┘
       │   invoice          │
       └──────────────── middleware ◀── poll ── ByD outbound delivery / issued purchase order
Restroworks POS ──GRN / return / wastage──▶ middleware ──Celery──▶ ByD inbound delivery / goods consumption
Restroworks POS ──sales──▶ middleware ──sales feed──▶ Blue Prism ──▶ Sales Validation
                           middleware ◀── validated sales (POST /api/v1/sales) ── Blue Prism
                           middleware ──daily sales job──▶ ByD accounting entries
```

## Endpoints

The full contract, with request and response schemas, is in [`openapi.yaml`](openapi.yaml) (OpenAPI 3.1). Restroworks and the SRP team can load it into Swagger UI, Postman or Stoplight.

### Pushed by Restroworks

Authentication is HTTP Basic, using a middleware service user in the Django group `restroworks`. Every reply is HTTP 200 with `{"Status": "Success"}`, or with `{"Status": "Fail", "Reason": "..."}` when the push was rejected, which is the format the Restroworks specification asks for. Sending the same document twice is safe: the second push is acknowledged and nothing is created again.

| Method and path | Purpose | Idempotency key |
|---|---|---|
| `POST /api/v1/pos/purchase-orders` | Approved POS purchase order. Replies with `TotalCasesMessage`, the total quantity accepted. | `poId` |
| `POST /api/v1/pos/grns` | GRN (stock entry) against an invoice we sent. | `storeId` + `transactionNumber` |
| `POST /api/v1/pos/vendor-returns` | Return to vendor against a PO. | `storeId` + `returnTransactionNo` |
| `POST /api/v1/pos/wastage` | Wastage, using the schema below. | `storeId` + `wastagePrefix` + `wastageNumber` |
| `POST /api/v1/pos/sales` | A store's sales for one business date, using the schema below. | `storeId` + `businessDate` (a later push replaces the day) |

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

**Sales schema (defined by us):**

```json
{
  "storeId": "3727",
  "customerKey": "630b9e...",
  "businessDate": "2026-10-22",
  "tenders": [
    {"paymentType": "CASH", "amount": 528300},
    {"paymentType": "DEBIT CARD", "amount": 541700},
    {"paymentType": "BANK TRANSFER", "amount": 148700},
    {"paymentType": "CREDIT", "amount": 3500}
  ]
}
```

- One push carries the store's whole business day, as totals by payment type. A later push for the same store and date replaces the earlier one.
- `paymentType` must be the tender name Blue Prism reconciles on, as ICG sends it: `CASH`, `DEBIT CARD`, `CREDIT`, `BANK TRANSFER` or `STAFF MEAL`. Names are upper-cased, and repeated payment types are added together.
- `amount` is in naira, with at most 2 decimal places.
- Nothing goes to ByD from this push. The sales reach ByD only after validation, through `POST /api/v1/sales` and the daily sales job, as today.

### Called by the Store Requisition Portal

| Method and path | Purpose |
|---|---|
| `POST /srp-feed/token` | Token endpoint compatible with ICG's `/token` (form fields `grant_type=password`, `username`, `password`). Only users in the group `store_requisition` get a token. It lasts 14 days and opens the feed only. |
| `GET /srp-feed/api/FoodConcept/StoreRequest/<YYYY-MM-DD>` | POS purchase orders received that day, in the same shape SRP reads from ICG. Lines arrive already approved (`is_declined: false`). |
| `POST /api/v1/pos/purchase-orders/link` | Basic auth (SRP's existing middleware user, in group `store_requisition`) or JWT. After SRP syncs an order to ByD, it reports which POS purchase order lines went into which ByD document. |

Link body:

```json
{
  "document_type": "sales_order",
  "document_id": "5001",
  "lines": [{"warehouse": "W101", "series": "BP/O1-19-20/", "orderID": 158, "reference": "10047", "quantity": 10}]
}
```

`document_type` is one of `sales_order`, `purchase_request` or `purchase_order`.

### Called by Blue Prism

These copy ICG's interface, so Blue Prism only changes its base URL (to `<middleware>/sales-feed`) and its credentials.

| Method and path | Purpose |
|---|---|
| `POST /sales-feed/token` | Token endpoint compatible with ICG's `/token` (form fields `grant_type=password`, `username`, `password`). Only users in the group `blue_prism` get a token. It lasts 14 days and opens the sales feed only. |
| `GET /sales-feed/api/FoodConcept/Sales/<YYYY-MM-DD>` | The POS sales for that business date, in ICG's format: one row per store and payment type, `{"warehouseCode", "warehouseName", "date", "paymentType", "amount"}`, with the amount as text. `warehouseCode` is the store's ICG warehouse code, so the validated sales Blue Prism sends to `POST /api/v1/sales` still match the store. |

The raw sales are listed in the admin under **Pos sales**, with how many times each day was pushed.

### Called on Restroworks

`sync_dispatches` runs every `POS_DISPATCH_POLL_SECONDS` and sends invoices to `RESTROWORKS_INVOICE_URL?customer_key=<outlet key>`:

- **Warehouse, CK or PPU (sales order):**
  - One invoice per released ByD outbound delivery, carrying the quantities actually shipped.
  - Cancelled deliveries, and deliveries not yet released, are skipped.
  - The invoice number is `<delivery ID>-<storeId>-<poNumber>`.
- **Direct vendor (purchase order):**
  - One invoice once the ByD PO is issued (status 6 or 9), carrying the final quantities and prices.
  - The invoice number is `PO<ByD PO ID>-<storeId>-<poNumber>`.

When one ByD document covers several POS purchase orders, each PO is invoiced in turn, in PO order. It gets what the ByD document holds for its lines, up to what it still has outstanding.

## Deployment

The middleware, including this app, runs with Docker Compose behind NGINX. See `DEPLOYMENT.md` at the repository root.
