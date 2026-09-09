# Demo Scenarios

These scenarios assume the API is running locally.

Start the MVP:

```powershell
docker compose up --build
```

Open the operator console:

```text
http://127.0.0.1:8000/
```

Swagger is still available for API schema inspection:

```text
http://127.0.0.1:8000/docs
```

## Scenario 1: Happy Path

Run:

```powershell
.\scripts\demo_happy_path.ps1
```

This demonstrates:

- order intake
- inventory allocation
- pick task creation
- pick completion
- pack
- ship
- shipment confirmation publish success
- final order status `CONFIRMATION_PUBLISHED`

Expected status flow:

```text
PICKING -> PICKED -> PACKED -> SHIPPED -> CONFIRMATION_PUBLISHED
```

## Scenario 2: Retry and DLQ

Run:

```powershell
.\scripts\demo_retry_and_dlq.ps1
```

This demonstrates:

- transient OMS failure
- retry scheduling
- manual retry success
- permanent OMS failure
- mock DLQ record creation

Expected integration flow:

```text
TRANSIENT_FAILURE -> RETRY_SCHEDULED -> retry SUCCESS -> PUBLISHED
PERMANENT_FAILURE -> DEAD_LETTERED
```

## Scenario 3: Short Pick

In the operator console:

1. Select `Short pick` and create an order for quantity `2`.
2. Set the picked quantity to `1` and complete the pick task.
3. Select `Cancel remainder` to release the unpicked allocation.
4. Pack and ship the picked remainder.
5. Publish the shipment confirmation.

Expected result:

```text
pick task status: SHORT_PICK
order status: SHORT_PICK
resolved order status: SHORT_PICK_RESOLVED
shipment quantity: 1
cancelled quantity: 1
```

Packing before resolution returns a conflict; packing after resolution succeeds.

## Scenario 4: Idempotency

Send the same `POST /orders` request twice with the same `X-Idempotency-Key`.

Expected result:

```text
first response: 201 Created
second response: 200 OK
same order_id
idempotency_replayed: true
inventory is not allocated twice
```

Send a different request body with the same `X-Idempotency-Key`.

Expected result:

```text
409 Conflict
```

## Scenario 5: Inventory Rejection

Create an order with:

```json
{
  "external_order_id": "OMS-REJECT-1",
  "warehouse_id": "WH-02",
  "lines": [
    {
      "sku": "SKU-RED-SHIRT",
      "quantity": 5
    }
  ]
}
```

Expected result:

```text
409 Conflict
requested 5, available 4
```
