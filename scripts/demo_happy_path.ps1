param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Sku = "SKU-RED-SHIRT"
)

$ErrorActionPreference = "Stop"
$runId = [guid]::NewGuid().ToString('N')
$correlationId = "demo-corr-$runId"
$idempotencyKey = "demo-idem-happy-$runId"
$correlationHeaders = @{
    "X-Correlation-ID" = $correlationId
}
$orderHeaders = @{
    "X-Idempotency-Key" = $idempotencyKey
    "X-Correlation-ID" = $correlationId
}

$orderBody = @{
    external_order_id = "OMS-DEMO-HAPPY-$runId"
    warehouse_id = "WH-01"
    customer_id = "CUST-DEMO"
    lines = @(
        @{
            sku = $Sku
            quantity = 2
        }
    )
} | ConvertTo-Json -Depth 5

$order = Invoke-RestMethod `
    -Uri "$BaseUrl/orders" `
    -Method Post `
    -Headers $orderHeaders `
    -ContentType "application/json" `
    -Body $orderBody

$pick = Invoke-RestMethod `
    -Uri "$BaseUrl/warehouse/picks/$($order.pick_task_id)" `
    -Headers $correlationHeaders `
    -Method Get

$pickBody = @{
    lines = @(
        @{
            order_line_id = $pick.lines[0].order_line_id
            picked_quantity = $pick.lines[0].quantity_to_pick
        }
    )
} | ConvertTo-Json -Depth 5

$pickCompletion = Invoke-RestMethod `
    -Uri "$BaseUrl/warehouse/picks/$($order.pick_task_id)/complete" `
    -Method Post `
    -Headers $correlationHeaders `
    -ContentType "application/json" `
    -Body $pickBody

$pack = Invoke-RestMethod `
    -Uri "$BaseUrl/orders/$($order.order_id)/pack" `
    -Headers $correlationHeaders `
    -Method Post

$shipBody = @{
    carrier = "UPS"
    tracking_number = "1ZDEMO$runId"
} | ConvertTo-Json -Depth 5

$ship = Invoke-RestMethod `
    -Uri "$BaseUrl/orders/$($order.order_id)/ship" `
    -Method Post `
    -Headers $correlationHeaders `
    -ContentType "application/json" `
    -Body $shipBody

$publishBody = @{
    downstream_result = "SUCCESS"
} | ConvertTo-Json -Depth 5

$publish = Invoke-RestMethod `
    -Uri "$BaseUrl/integration/messages/$($ship.shipment_confirmation_message.message_id)/publish" `
    -Method Post `
    -Headers $correlationHeaders `
    -ContentType "application/json" `
    -Body $publishBody

$finalOrder = Invoke-RestMethod `
    -Uri "$BaseUrl/orders/$($order.order_id)" `
    -Headers $correlationHeaders `
    -Method Get

if ($finalOrder.status -ne 'CONFIRMATION_PUBLISHED' -or $publish.message.status -ne 'PUBLISHED') {
    throw 'Happy-path demo did not reach the expected final state.'
}

[PSCustomObject]@{
    correlation_id = $correlationId
    order_id = $order.order_id
    pick_task_id = $order.pick_task_id
    shipment_id = $pack.shipment.shipment_id
    message_id = $ship.shipment_confirmation_message.message_id
    order_after_create = $order.status
    order_after_pick = $pickCompletion.order_status
    order_after_pack = $pack.order.status
    order_after_ship = $ship.order.status
    message_after_publish = $publish.message.status
    final_order_status = $finalOrder.status
} | Format-List
