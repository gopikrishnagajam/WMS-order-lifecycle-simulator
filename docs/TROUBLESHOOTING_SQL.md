# Troubleshooting SQL

These investigation queries are meant for the Docker/PostgreSQL runtime path. Replace the sample values such as `OMS-1001`, `ORDER_ID_HERE`, and `CORRELATION_ID_HERE` before running them.

## Scenario 1: Trace an OMS order through the lifecycle

Business problem

An OMS order was received, and I need to see where it is in the WMS lifecycle across order intake, order lines, pick work, and shipment creation.

SQL query

```sql
SELECT
    o.external_order_id,
    o.order_id,
    o.status AS order_status,
    o.warehouse_id,
    o.correlation_id,
    ol.line_id AS order_line_id,
    ol.sku,
    ol.quantity AS requested_quantity,
    ol.allocated_quantity,
    ol.picked_quantity,
    ol.cancelled_quantity,
    pt.pick_task_id,
    pt.status AS pick_task_status,
    ptl.quantity_to_pick,
    ptl.picked_quantity AS task_picked_quantity,
    s.shipment_id,
    s.status AS shipment_status,
    s.carrier,
    s.tracking_number,
    sl.quantity AS shipped_quantity
FROM orders o
JOIN order_lines ol
    ON ol.order_id = o.order_id
LEFT JOIN pick_tasks pt
    ON pt.order_id = o.order_id
LEFT JOIN pick_task_lines ptl
    ON ptl.pick_task_id = pt.pick_task_id
   AND ptl.order_line_id = ol.line_id
LEFT JOIN shipments s
    ON s.order_id = o.order_id
LEFT JOIN shipment_lines sl
    ON sl.shipment_id = s.shipment_id
   AND sl.order_line_id = ol.line_id
WHERE o.external_order_id = 'OMS-1001'
ORDER BY ol.sku, ol.line_id;
```

What the result tells me

Each row shows one order line and the related warehouse execution state. Missing pick-task columns mean the order did not reach picking. Missing shipment columns mean it has not been packed/shipped yet. Quantity differences show whether the line was fully picked, short picked, cancelled, or shipped.

Next system/process I investigate

If no row is returned, check the OMS request and idempotency key. If the order exists but pick task data is missing, inspect order intake and allocation. If the pick is complete but shipment data is missing, inspect pack/ship processing.

## Scenario 2: Investigate an order that was not allocated

Business problem

An order was rejected or never moved into picking, and I need to know whether inventory existed, was stocked at the requested warehouse, or was already allocated to other orders.

SQL query

```sql
SELECT
    o.external_order_id,
    o.order_id,
    o.status AS order_status,
    o.warehouse_id,
    ol.sku,
    ol.quantity AS requested_quantity,
    ol.allocated_quantity AS order_allocated_quantity,
    i.on_hand_quantity,
    i.allocated_quantity AS inventory_allocated_quantity,
    i.on_hand_quantity - i.allocated_quantity AS available_quantity,
    CASE
        WHEN i.sku IS NULL THEN 'SKU not stocked at this warehouse'
        WHEN i.on_hand_quantity - i.allocated_quantity < ol.quantity THEN 'Insufficient available inventory'
        WHEN ol.allocated_quantity < ol.quantity THEN 'Order line was not fully allocated'
        ELSE 'Inventory appears allocatable'
    END AS allocation_diagnosis
FROM orders o
JOIN order_lines ol
    ON ol.order_id = o.order_id
LEFT JOIN inventory_items i
    ON i.warehouse_id = o.warehouse_id
   AND i.sku = ol.sku
WHERE o.order_id = 'ORDER_ID_HERE'
ORDER BY ol.sku, ol.line_id;
```

What the result tells me

The query compares demand on each order line with current inventory availability. It separates missing warehouse/SKU stocking problems from true insufficient inventory and from cases where the order line exists but was not allocated as expected.

Next system/process I investigate

If inventory is missing, inspect inventory setup/seed data. If available quantity is too low, inspect earlier allocations for the same SKU and warehouse. If inventory appears allocatable but the order was not allocated, inspect order intake validation and transaction handling.

## Scenario 3: Compare quantities after a short pick

Business problem

A picker reported a short pick, and I need to reconcile requested, allocated, picked, cancelled, and shipped quantities for the order.

SQL query

```sql
SELECT
    o.external_order_id,
    o.order_id,
    o.status AS order_status,
    ol.line_id AS order_line_id,
    ol.sku,
    ol.quantity AS requested_quantity,
    ol.allocated_quantity,
    ol.picked_quantity,
    ol.cancelled_quantity,
    ol.quantity - ol.picked_quantity - ol.cancelled_quantity AS unresolved_quantity,
    pt.status AS pick_task_status,
    ptl.quantity_to_pick,
    ptl.picked_quantity AS task_picked_quantity,
    COALESCE(sl.quantity, 0) AS shipped_quantity
FROM orders o
JOIN order_lines ol
    ON ol.order_id = o.order_id
LEFT JOIN pick_tasks pt
    ON pt.order_id = o.order_id
LEFT JOIN pick_task_lines ptl
    ON ptl.pick_task_id = pt.pick_task_id
   AND ptl.order_line_id = ol.line_id
LEFT JOIN shipments s
    ON s.order_id = o.order_id
LEFT JOIN shipment_lines sl
    ON sl.shipment_id = s.shipment_id
   AND sl.order_line_id = ol.line_id
WHERE o.order_id = 'ORDER_ID_HERE'
ORDER BY ol.sku, ol.line_id;
```

What the result tells me

For a resolved short pick, `picked_quantity + cancelled_quantity` should equal the original requested quantity. `allocated_quantity` should match the picked quantity after `CANCEL_REMAINDER`, and `unresolved_quantity` should be zero. If shipped, shipment-line quantity should match the picked quantity.

Next system/process I investigate

If unresolved quantity remains, inspect short-pick resolution. If pick-task quantities do not match order-line picked quantities, inspect warehouse pick completion. If shipment quantity differs from picked quantity, inspect pack/ship creation.

## Scenario 4: Find shipped orders without a published shipment confirmation

Business problem

The warehouse shipped an order, but the OMS may not have received the shipment confirmation.

SQL query

```sql
SELECT
    o.external_order_id,
    o.order_id,
    o.status AS order_status,
    o.correlation_id,
    s.shipment_id,
    s.status AS shipment_status,
    s.shipped_at,
    im.message_id,
    im.status AS message_status,
    im.attempt_count,
    im.max_attempts,
    im.next_retry_at,
    im.last_error
FROM orders o
JOIN shipments s
    ON s.order_id = o.order_id
LEFT JOIN integration_messages im
    ON im.message_type = 'SHIPMENT_CONFIRMATION'
   AND im.correlation_id = o.correlation_id
   AND im.payload ->> 'order_id' = o.order_id
WHERE o.status = 'SHIPPED'
  AND s.status = 'SHIPPED'
  AND COALESCE(im.status, 'MISSING') <> 'PUBLISHED'
ORDER BY s.shipped_at DESC;
```

What the result tells me

These orders are physically shipped but have no published confirmation message. A missing `message_id` points to message creation. `PENDING` points to an unpublished message. `RETRY_SCHEDULED` points to a downstream failure waiting for retry. `DEAD_LETTERED` means the message failed permanently or exhausted retry attempts.

Next system/process I investigate

For missing messages, inspect the ship endpoint and transaction that creates integration messages. For retry or dead-letter statuses, inspect the integration publish result, `last_error`, and downstream OMS availability.

## Scenario 5: Trace retry and DLQ messages by correlation ID

Business problem

A shipment confirmation failed or went to the DLQ, and I need to trace the failed message back to the original order and shipment.

SQL query

```sql
SELECT
    o.external_order_id,
    o.order_id,
    o.status AS order_status,
    s.shipment_id,
    s.status AS shipment_status,
    im.message_id,
    im.status AS message_status,
    im.attempt_count,
    im.max_attempts,
    im.next_retry_at,
    im.last_error,
    dlq.dead_letter_id,
    dlq.reason AS dlq_reason,
    dlq.final_attempt_count,
    dlq.failed_at
FROM integration_messages im
LEFT JOIN dead_letter_messages dlq
    ON dlq.original_message_id = im.message_id
LEFT JOIN orders o
    ON o.correlation_id = im.correlation_id
LEFT JOIN shipments s
    ON s.order_id = o.order_id
WHERE im.correlation_id = 'CORRELATION_ID_HERE'
  AND im.status IN ('RETRY_SCHEDULED', 'DEAD_LETTERED')
ORDER BY im.created_at, dlq.failed_at;
```

What the result tells me

The result shows whether the message is still retryable or has reached the DLQ. `attempt_count`, `max_attempts`, and `next_retry_at` show retry state. DLQ columns explain why the message was finalized as failed.

Next system/process I investigate

For `RETRY_SCHEDULED`, inspect the retry path and downstream OMS behavior before the next attempt. For `DEAD_LETTERED`, inspect the DLQ record, payload, and OMS rejection reason before replaying or manually correcting the shipment confirmation.
