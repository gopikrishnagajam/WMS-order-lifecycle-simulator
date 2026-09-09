const state = {
  activeTab: "orders",
  orders: [],
  inventory: [],
  picks: [],
  shipments: [],
  messages: [],
  dlq: [],
  selectedOrder: null,
  selectedPick: null,
};

const lifecycleStates = ["PICKING", "PICKED", "SHORT_PICK", "SHORT_PICK_RESOLVED", "CANCELLED", "PACKED", "SHIPPED", "CONFIRMATION_PUBLISHED"];
const scenarioDefaults = { full: 0, short: 1 };

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
const statusBadge = (status) => `<span class="status status-${String(status).toLowerCase()}">${escapeHtml(status)}</span>`;
const shortId = (value) => value ? `${value.slice(0, 8)}...` : "-";

function correlationId() {
  return `ui-${crypto.randomUUID()}`;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Correlation-ID", correlationId());
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  showTrace(`${options.method || "GET"} ${path}`, body, response.status);
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function showTrace(route, body, status) {
  $("#trace-route").textContent = `${status}  ${route}`;
  $("#trace-output").textContent = JSON.stringify(body, null, 2);
}

function notice(message = "") {
  $("#notice").textContent = message;
}

async function refreshAll() {
  notice();
  const results = await Promise.allSettled([
    api("/health/ready"),
    api("/orders"),
    api("/inventory"),
    api("/warehouse/picks"),
    api("/shipments"),
    api("/integration/messages"),
    api("/integration/dlq"),
  ]);
  const [health, orders, inventory, picks, shipments, messages, dlq] = results;
  if (health.status === "fulfilled") {
    $("#database-status").textContent = `Database ready / ${health.value.environment}`;
    $("#database-status").classList.remove("error");
  } else {
    $("#database-status").textContent = "API unavailable";
    $("#database-status").classList.add("error");
  }
  if (orders.status === "fulfilled") state.orders = orders.value;
  if (inventory.status === "fulfilled") state.inventory = inventory.value;
  if (picks.status === "fulfilled") state.picks = picks.value;
  if (shipments.status === "fulfilled") state.shipments = shipments.value;
  if (messages.status === "fulfilled") state.messages = messages.value;
  if (dlq.status === "fulfilled") state.dlq = dlq.value;
  const failed = results.find((result) => result.status === "rejected");
  if (failed) notice(failed.reason.message);
  if (state.selectedOrder) {
    const refreshed = state.orders.find((order) => order.order_id === state.selectedOrder.order_id);
    state.selectedOrder = refreshed || null;
    if (state.selectedOrder?.pick_task_id) await loadPick(state.selectedOrder.pick_task_id, false);
  }
  render();
}

async function loadPick(pickTaskId, redraw = true) {
  try {
    state.selectedPick = await api(`/warehouse/picks/${pickTaskId}`);
    if (redraw) render();
  } catch (error) {
    notice(error.message);
  }
}

async function selectOrder(orderId) {
  try {
    state.selectedOrder = await api(`/orders/${orderId}`);
    if (state.selectedOrder.pick_task_id) await loadPick(state.selectedOrder.pick_task_id, false);
    render();
  } catch (error) {
    notice(error.message);
  }
}

function render() {
  $("#metric-orders").textContent = state.orders.length;
  $("#metric-picks").textContent = state.picks.filter((pick) => pick.status === "OPEN").length;
  $("#metric-available").textContent = state.inventory.reduce((sum, item) => sum + item.available_quantity, 0);
  $("#metric-messages").textContent = state.messages.filter((message) => ["PENDING", "RETRY_SCHEDULED"].includes(message.status)).length;
  renderFlow();
  renderQueue();
}

function renderFlow() {
  const order = state.selectedOrder;
  if (!order) {
    $("#flow-empty").classList.remove("hidden");
    $("#flow-content").classList.add("hidden");
    $("#selected-order-title").textContent = "Choose an order";
    $("#selected-order-status").className = "status status-muted";
    $("#selected-order-status").textContent = "Idle";
    return;
  }
  $("#flow-empty").classList.add("hidden");
  $("#flow-content").classList.remove("hidden");
  $("#selected-order-title").textContent = order.external_order_id;
  $("#selected-order-status").className = `status status-${String(order.status).toLowerCase()}`;
  $("#selected-order-status").textContent = order.status;
  $("#order-summary").innerHTML = `<div><strong>${escapeHtml(order.external_order_id)}</strong><small>${escapeHtml(order.order_id)} &middot; ${escapeHtml(order.warehouse_id)}</small></div><div class="summary-meta"><span>${order.lines.length} line${order.lines.length === 1 ? "" : "s"}</span><span>${escapeHtml(order.customer_id || "No customer")}</span></div>`;
  const current = order.status;
  const currentIndex = lifecycleStates.indexOf(current);
  $("#lifecycle").innerHTML = lifecycleStates.map((step, index) => `<div class="lifecycle-step ${index < currentIndex ? "done" : ""} ${index === currentIndex ? "current" : ""}"><span class="marker"></span><span>${step.replaceAll("_", " ")}</span></div>`).join("");
  $("#flow-action").innerHTML = actionMarkup(order);
  bindActionHandlers(order);
}

function actionMarkup(order) {
  if (order.status === "PICKING" && state.selectedPick) {
    return `<div class="action-heading"><strong>Complete pick task</strong><span>${statusBadge(state.selectedPick.status)}</span></div><div class="pick-lines">${state.selectedPick.lines.map((line) => `<label class="pick-line"><span><strong>${escapeHtml(line.sku)}</strong>Pick up to ${line.quantity_to_pick}</span><input class="picked-quantity" data-line-id="${line.order_line_id}" type="number" min="0" max="${line.quantity_to_pick}" value="${scenarioDefaults[$("#scenario-mode")?.value || "full"] === 1 ? Math.max(0, line.quantity_to_pick - 1) : line.quantity_to_pick}"></label>`).join("")}</div><div class="action-buttons"><button id="complete-pick" class="button button-primary" type="button">Complete pick</button></div>`;
  }
  if (order.status === "SHORT_PICK") {
    return `<div class="action-heading"><strong>Short pick needs resolution</strong><span>${order.lines.reduce((sum, line) => sum + line.quantity - line.picked_quantity, 0)} units unpicked</span></div><p class="muted-cell">The cancel remainder policy releases unpicked allocation and ships only picked units.</p><div class="action-buttons"><button id="resolve-short-pick" class="button button-primary" type="button">Cancel remainder</button></div>`;
  }
  if (["PICKED", "SHORT_PICK_RESOLVED"].includes(order.status)) {
    return `<div class="action-heading"><strong>Ready to pack</strong><span>Picked units become a shipment.</span></div><div class="action-buttons"><button id="pack-order" class="button button-primary" type="button">Pack order</button></div>`;
  }
  if (order.status === "PACKED") {
    return `<div class="action-heading"><strong>Ready to ship</strong><span>Inventory is consumed at shipment.</span></div><div class="inline-inputs"><label>Carrier<input id="carrier" value="UPS"></label><label>Tracking number<input id="tracking-number" placeholder="Auto-generate"></label></div><div class="action-buttons"><button id="ship-order" class="button button-primary" type="button">Ship order</button></div>`;
  }
  if (order.status === "SHIPPED") {
    const message = state.messages.find((item) => item.payload?.order_id === order.order_id || item.correlation_id === order.correlation_id);
    return `<div class="action-heading"><strong>Shipment confirmation</strong><span>${message ? statusBadge(message.status) : "Message loading"}</span></div><div class="action-buttons">${message && ["PENDING", "RETRY_SCHEDULED"].includes(message.status) ? `<button class="button button-primary" data-message-action="success" data-message-id="${message.message_id}" type="button">Publish success</button>` : ""}</div>`;
  }
  if (order.status === "CONFIRMATION_PUBLISHED") return `<div class="action-heading"><strong>Lifecycle complete</strong><span>Confirmation published to OMS.</span></div>`;
  if (order.status === "CANCELLED") return `<div class="action-heading"><strong>Order cancelled</strong><span>No picked units to fulfill.</span></div>`;
  return `<div class="muted-cell">No action available for ${escapeHtml(order.status)}.</div>`;
}

function bindActionHandlers(order) {
  $("#complete-pick")?.addEventListener("click", async () => {
    const lines = [...document.querySelectorAll(".picked-quantity")].map((input) => ({ order_line_id: input.dataset.lineId, picked_quantity: Number(input.value) }));
    await runAction(() => api(`/warehouse/picks/${order.pick_task_id}/complete`, { method: "POST", body: JSON.stringify({ lines }) }));
  });
  $("#resolve-short-pick")?.addEventListener("click", async () => {
    await runAction(() => api(`/orders/${order.order_id}/resolve-short-pick`, { method: "POST", body: JSON.stringify({ policy: "CANCEL_REMAINDER" }) }));
  });
  $("#pack-order")?.addEventListener("click", async () => {
    await runAction(() => api(`/orders/${order.order_id}/pack`, { method: "POST" }));
  });
  $("#ship-order")?.addEventListener("click", async () => {
    await runAction(() => api(`/orders/${order.order_id}/ship`, { method: "POST", body: JSON.stringify({ carrier: $("#carrier").value, tracking_number: $("#tracking-number").value || null }) }));
  });
  document.querySelector("[data-message-action]")?.addEventListener("click", async (event) => {
    await processMessage(event.currentTarget.dataset.messageId, "SUCCESS", "publish");
  });
}

async function runAction(action) {
  try {
    const response = await action();
    if (response.order?.order_id) state.selectedOrder = response.order;
    else if (response.order_id) state.selectedOrder = response;
    await refreshAll();
    notice("Operation completed.");
  } catch (error) { notice(error.message); }
}

function renderQueue() {
  const content = $("#queue-content");
  if (state.activeTab === "orders") content.innerHTML = ordersTable();
  if (state.activeTab === "inventory") content.innerHTML = inventoryTable();
  if (state.activeTab === "picks") content.innerHTML = picksTable();
  if (state.activeTab === "shipments") content.innerHTML = shipmentsTable();
  if (state.activeTab === "integration") content.innerHTML = integrationTable();
  content.querySelectorAll("[data-order-id]:not([data-pick-id]):not([data-shipment-id])").forEach((row) => row.addEventListener("click", () => selectOrder(row.dataset.orderId)));
  content.querySelectorAll("[data-pick-id]").forEach((row) => row.addEventListener("click", () => selectOrder(row.dataset.orderId)));
  content.querySelectorAll("[data-shipment-id]").forEach((row) => row.addEventListener("click", async () => {
    await selectOrder(row.dataset.orderId);
    try { await api(`/shipments/${row.dataset.shipmentId}`); } catch (error) { notice(error.message); }
  }));
  content.querySelectorAll("[data-message-id]").forEach((button) => button.addEventListener("click", (event) => { event.stopPropagation(); processMessage(button.dataset.messageId, button.dataset.result, button.dataset.operation); }));
}

function ordersTable() {
  if (!state.orders.length) return `<div class="table-empty">No orders in the database.</div>`;
  return `<div class="table-scroll"><table class="data-table"><thead><tr><th>External ID</th><th>Status</th><th>Warehouse</th><th>Lines</th><th>Created</th></tr></thead><tbody>${state.orders.map((order) => `<tr class="selectable ${state.selectedOrder?.order_id === order.order_id ? "selected" : ""}" data-order-id="${order.order_id}"><td class="primary-cell">${escapeHtml(order.external_order_id)}<br><span class="muted-cell">${shortId(order.order_id)}</span></td><td>${statusBadge(order.status)}</td><td>${escapeHtml(order.warehouse_id)}</td><td>${order.lines.reduce((sum, line) => sum + line.quantity, 0)}</td><td class="muted-cell">${formatDate(order.created_at)}</td></tr>`).join("")}</tbody></table></div>`;
}

function inventoryTable() {
  return `<div class="table-scroll"><table class="data-table"><thead><tr><th>SKU</th><th>Warehouse</th><th>On hand</th><th>Allocated</th><th>Available</th></tr></thead><tbody>${state.inventory.map((item) => `<tr><td class="primary-cell">${escapeHtml(item.sku)}<br><span class="muted-cell">${escapeHtml(item.description)}</span></td><td>${escapeHtml(item.warehouse_id)}</td><td>${item.on_hand_quantity}</td><td>${item.allocated_quantity}</td><td><strong>${item.available_quantity}</strong></td></tr>`).join("")}</tbody></table></div>`;
}

function picksTable() {
  if (!state.picks.length) return `<div class="table-empty">No pick tasks in the database.</div>`;
  return `<div class="table-scroll"><table class="data-table"><thead><tr><th>Pick task</th><th>Order</th><th>Status</th><th>Units</th><th>Created</th></tr></thead><tbody>${state.picks.map((pick) => `<tr class="selectable" data-pick-id="${pick.pick_task_id}" data-order-id="${pick.order_id}"><td class="primary-cell">${shortId(pick.pick_task_id)}</td><td>${shortId(pick.order_id)}</td><td>${statusBadge(pick.status)}</td><td>${pick.lines.reduce((sum, line) => sum + line.quantity_to_pick, 0)}</td><td class="muted-cell">${formatDate(pick.created_at)}</td></tr>`).join("")}</tbody></table></div>`;
}

function shipmentsTable() {
  if (!state.shipments.length) return `<div class="table-empty">No shipments in the database.</div>`;
  return `<div class="table-scroll"><table class="data-table"><thead><tr><th>Shipment</th><th>Order</th><th>Status</th><th>Carrier</th><th>Lines</th></tr></thead><tbody>${state.shipments.map((shipment) => `<tr class="selectable" data-order-id="${shipment.order_id}" data-shipment-id="${shipment.shipment_id}"><td class="primary-cell">${shortId(shipment.shipment_id)}</td><td>${shortId(shipment.order_id)}</td><td>${statusBadge(shipment.status)}</td><td>${escapeHtml(shipment.carrier || "-")}</td><td>${shipment.lines.reduce((sum, line) => sum + line.quantity, 0)}</td></tr>`).join("")}</tbody></table></div>`;
}

function integrationTable() {
  const messages = state.messages.map((message) => `<tr><td class="primary-cell">${shortId(message.message_id)}<br><span class="muted-cell">${escapeHtml(message.message_type)}</span></td><td>${statusBadge(message.status)}</td><td>${message.attempt_count} / ${message.max_attempts}</td><td class="muted-cell">${escapeHtml(message.last_error || "-")}</td><td><div class="table-actions">${["PENDING", "RETRY_SCHEDULED"].includes(message.status) ? `<select class="table-select" data-message-select="${message.message_id}"><option value="SUCCESS">Success</option><option value="TRANSIENT_FAILURE">Transient failure</option><option value="PERMANENT_FAILURE">Permanent failure</option></select><button class="button" data-message-id="${message.message_id}" data-operation="${message.status === "RETRY_SCHEDULED" ? "retry" : "publish"}" data-result="SUCCESS" type="button">${message.status === "RETRY_SCHEDULED" ? "Retry" : "Publish"}</button>` : ""}</div></td></tr>`).join("");
  const deadLetters = state.dlq.map((item) => `<tr><td class="primary-cell">DLQ ${shortId(item.dead_letter_id)}</td><td>${statusBadge("DEAD_LETTERED")}</td><td>${escapeHtml(item.reason)}</td><td>${item.final_attempt_count}</td><td></td></tr>`).join("");
  if (!messages && !deadLetters) return `<div class="table-empty">No integration messages or dead letters.</div>`;
  return `<div class="table-scroll"><table class="data-table"><thead><tr><th>Message</th><th>Status</th><th>Attempts</th><th>Last error / reason</th><th>Action</th></tr></thead><tbody>${messages || ""}${deadLetters || ""}</tbody></table></div>`;
}

async function processMessage(messageId, result, operation) {
  const select = document.querySelector(`[data-message-select="${messageId}"]`);
  const downstreamResult = select?.value || result;
  try {
    await api(`/integration/messages/${messageId}/${operation}`, { method: "POST", body: JSON.stringify({ downstream_result: downstreamResult, error_message: downstreamResult === "SUCCESS" ? null : "Simulated UI downstream failure" }) });
    await refreshAll();
    notice("Integration message processed.");
  } catch (error) { notice(error.message); }
}

function formatDate(value) { return value ? new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "-"; }

function addLine(defaultSku = "SKU-RED-SHIRT", defaultQuantity = 1) {
  const row = document.createElement("div");
  row.className = "line-row";
  row.innerHTML = `<input class="line-sku" value="${defaultSku}" aria-label="SKU" required><input class="line-quantity" type="number" min="1" value="${defaultQuantity}" aria-label="Quantity" required><button class="remove-line" type="button" aria-label="Remove line">x</button>`;
  row.querySelector(".remove-line").addEventListener("click", () => { if ($$(".line-row").length > 1) row.remove(); });
  $("#order-lines").appendChild(row);
}

function $$(selector) { return document.querySelectorAll(selector); }

$("#order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const key = `ui-${crypto.randomUUID()}`;
  const lines = [...$$(".line-row")].map((row) => ({ sku: row.querySelector(".line-sku").value.trim(), quantity: Number(row.querySelector(".line-quantity").value) }));
  try {
    const order = await api("/orders", { method: "POST", headers: { "X-Idempotency-Key": key }, body: JSON.stringify({ external_order_id: $("#external-order-id").value.trim(), warehouse_id: $("#warehouse-id").value, customer_id: $("#customer-id").value.trim() || null, lines }) });
    state.selectedOrder = order;
    await refreshAll();
    await selectOrder(order.order_id);
    notice("Order allocated and pick task created.");
    $("#external-order-id").value = `OMS-${Date.now().toString().slice(-6)}`;
  } catch (error) { notice(error.message); }
});

$("#add-line").addEventListener("click", () => addLine("SKU-BLUE-HAT", 1));
$("#refresh-button").addEventListener("click", refreshAll);
$("#scenario-mode").addEventListener("change", () => { if (state.selectedOrder) renderFlow(); });
document.querySelectorAll("[data-tab]").forEach((tab) => tab.addEventListener("click", () => { state.activeTab = tab.dataset.tab; document.querySelectorAll("[data-tab]").forEach((item) => item.classList.toggle("active", item === tab)); renderQueue(); }));

$("#external-order-id").value = `OMS-${Date.now().toString().slice(-6)}`;
addLine();
refreshAll();
