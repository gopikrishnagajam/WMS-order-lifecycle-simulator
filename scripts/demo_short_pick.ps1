param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Sku = "SKU-GREEN-SOCKS"
)

$ErrorActionPreference = "Stop"
$runId = [guid]::NewGuid().ToString('N')
$headers = @{ 'X-Correlation-ID' = "demo-short-$runId"; 'X-Idempotency-Key' = "short-$runId" }

function Get-DemoInventory {
    (Invoke-RestMethod "$BaseUrl/inventory?warehouse_id=WH-01") |
        Where-Object { $_.sku -eq $Sku } | Select-Object -First 1
}

$before = @(Get-DemoInventory)
$beforeOnHand = [int]$before[0].on_hand_quantity
$beforeAllocated = [int]$before[0].allocated_quantity
$body = @{
    external_order_id = "OMS-SHORT-$runId"
    warehouse_id = 'WH-01'
    lines = @(@{ sku = $Sku; quantity = 3 })
} | ConvertTo-Json -Depth 5
$order = Invoke-RestMethod "$BaseUrl/orders" -Method Post -Headers $headers -ContentType 'application/json' -Body $body
$pickBody = @{ lines = @(@{ order_line_id = $order.lines[0].line_id; picked_quantity = 1 }) } | ConvertTo-Json -Depth 5
$pick = Invoke-RestMethod "$BaseUrl/warehouse/picks/$($order.pick_task_id)/complete" -Method Post -Headers $headers -ContentType 'application/json' -Body $pickBody
$resolution = Invoke-RestMethod "$BaseUrl/orders/$($order.order_id)/resolve-short-pick" -Method Post -Headers $headers -ContentType 'application/json' -Body '{"policy":"CANCEL_REMAINDER"}'
$replay = Invoke-RestMethod "$BaseUrl/orders/$($order.order_id)/resolve-short-pick" -Method Post -Headers $headers -ContentType 'application/json' -Body '{"policy":"CANCEL_REMAINDER"}'
$pack = Invoke-RestMethod "$BaseUrl/orders/$($order.order_id)/pack" -Method Post -Headers $headers
$ship = Invoke-RestMethod "$BaseUrl/orders/$($order.order_id)/ship" -Method Post -Headers $headers -ContentType 'application/json' -Body '{"carrier":"UPS"}'
$messageId = $ship.shipment_confirmation_message.message_id
$publish = Invoke-RestMethod "$BaseUrl/integration/messages/$messageId/publish" -Method Post -Headers $headers -ContentType 'application/json' -Body '{"downstream_result":"SUCCESS"}'
$finalOrder = Invoke-RestMethod "$BaseUrl/orders/$($order.order_id)" -Headers $headers
$after = @(Get-DemoInventory)
$afterOnHand = [int]$after[0].on_hand_quantity
$afterAllocated = [int]$after[0].allocated_quantity

if ($pick.order_status -ne 'SHORT_PICK' -or $resolution.status -ne 'SHORT_PICK_RESOLVED' -or
    $resolution.lines[0].cancelled_quantity -ne 2 -or $replay.status -ne 'SHORT_PICK_RESOLVED' -or
    $pack.shipment.lines[0].quantity -ne 1 -or $finalOrder.status -ne 'CONFIRMATION_PUBLISHED' -or
    $afterOnHand -ne ($beforeOnHand - 1) -or
    $afterAllocated -ne $beforeAllocated) {
    throw 'Short-pick demo failed its lifecycle or inventory assertions.'
}

[PSCustomObject]@{
    order_id = $order.order_id
    after_pick = $pick.order_status
    after_resolution = $resolution.status
    ordered_quantity = 3
    shipped_quantity = $pack.shipment.lines[0].quantity
    cancelled_quantity = $resolution.lines[0].cancelled_quantity
    final_order_status = $finalOrder.status
    on_hand_before = $beforeOnHand
    on_hand_after = $afterOnHand
    allocated_before = $beforeAllocated
    allocated_after = $afterAllocated
} | Format-List
