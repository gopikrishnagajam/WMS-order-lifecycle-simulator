param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Sku = "SKU-RED-SHIRT"
)

$ErrorActionPreference = "Stop"

function New-ShippedDemoOrder {
    param(
        [string]$BaseUrl,
        [string]$RunId,
        [string]$ScenarioName,
        [string]$Sku
    )

    $correlationId = "demo-corr-$ScenarioName-$RunId"
    $idempotencyKey = "demo-idem-$ScenarioName-$RunId"
    $correlationHeaders = @{
        "X-Correlation-ID" = $correlationId
    }
    $orderHeaders = @{
        "X-Idempotency-Key" = $idempotencyKey
        "X-Correlation-ID" = $correlationId
    }
    $orderBody = @{
        external_order_id = "OMS-DEMO-$ScenarioName-$RunId"
        warehouse_id = "WH-01"
        customer_id = "CUST-DEMO"
        lines = @(
            @{
                sku = $Sku
                quantity = 1
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

    Invoke-RestMethod `
        -Uri "$BaseUrl/warehouse/picks/$($order.pick_task_id)/complete" `
        -Method Post `
        -Headers $correlationHeaders `
        -ContentType "application/json" `
        -Body $pickBody | Out-Null

    Invoke-RestMethod `
        -Uri "$BaseUrl/orders/$($order.order_id)/pack" `
        -Headers $correlationHeaders `
        -Method Post | Out-Null

    $shipBody = @{
        carrier = "UPS"
        tracking_number = "1Z$ScenarioName$RunId"
    } | ConvertTo-Json -Depth 5

    return Invoke-RestMethod `
        -Uri "$BaseUrl/orders/$($order.order_id)/ship" `
        -Method Post `
        -Headers $correlationHeaders `
        -ContentType "application/json" `
        -Body $shipBody
}

$runId = [guid]::NewGuid().ToString('N')
$retryHeaders = @{
    "X-Correlation-ID" = "demo-corr-RETRY-$runId"
}
$dlqHeaders = @{
    "X-Correlation-ID" = "demo-corr-DLQ-$runId"
}

$retryShip = New-ShippedDemoOrder `
    -BaseUrl $BaseUrl `
    -RunId $runId `
    -ScenarioName "RETRY" `
    -Sku $Sku

$transientBody = @{
    downstream_result = "TRANSIENT_FAILURE"
    error_message = "OMS timeout"
} | ConvertTo-Json -Depth 5

$transient = Invoke-RestMethod `
    -Uri "$BaseUrl/integration/messages/$($retryShip.shipment_confirmation_message.message_id)/publish" `
    -Method Post `
    -Headers $retryHeaders `
    -ContentType "application/json" `
    -Body $transientBody

$successBody = @{
    downstream_result = "SUCCESS"
} | ConvertTo-Json -Depth 5

$retrySuccess = Invoke-RestMethod `
    -Uri "$BaseUrl/integration/messages/$($retryShip.shipment_confirmation_message.message_id)/retry" `
    -Method Post `
    -Headers $retryHeaders `
    -ContentType "application/json" `
    -Body $successBody

$publishedOrder = Invoke-RestMethod `
    -Uri "$BaseUrl/orders/$($retryShip.order.order_id)" `
    -Headers $retryHeaders `
    -Method Get

$dlqShip = New-ShippedDemoOrder `
    -BaseUrl $BaseUrl `
    -RunId $runId `
    -ScenarioName "DLQ" `
    -Sku $Sku

$permanentBody = @{
    downstream_result = "PERMANENT_FAILURE"
    error_message = "OMS rejected payload"
} | ConvertTo-Json -Depth 5

$permanent = Invoke-RestMethod `
    -Uri "$BaseUrl/integration/messages/$($dlqShip.shipment_confirmation_message.message_id)/publish" `
    -Method Post `
    -Headers $dlqHeaders `
    -ContentType "application/json" `
    -Body $permanentBody

$dlqResponse = Invoke-WebRequest `
    -UseBasicParsing `
    -Uri "$BaseUrl/integration/dlq" `
    -Headers $dlqHeaders `
    -Method Get
$dlqCount = ([regex]::Matches($dlqResponse.Content, '"dead_letter_id"')).Count

if ($transient.message.status -ne 'RETRY_SCHEDULED' -or
    $retrySuccess.message.status -ne 'PUBLISHED' -or
    $publishedOrder.status -ne 'CONFIRMATION_PUBLISHED' -or
    $permanent.message.status -ne 'DEAD_LETTERED' -or $dlqCount -lt 1) {
    throw 'Retry/DLQ demo did not reach the expected states.'
}

[PSCustomObject]@{
    transient_status = $transient.message.status
    transient_attempt_count = $transient.message.attempt_count
    retry_status = $retrySuccess.message.status
    retry_attempt_count = $retrySuccess.message.attempt_count
    published_order_status = $publishedOrder.status
    permanent_status = $permanent.message.status
    dlq_count = $dlqCount
    latest_dlq_reason = $permanent.dead_letter.reason
} | Format-List
