const SVG_NS = "http://www.w3.org/2000/svg";

function el(tag, attrs = {}) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) e.setAttribute(key, value);
  return e;
}

function formatMoney(cents) {
  const sign = cents < 0 ? "-" : "";
  return `${sign}$${(Math.abs(cents) / 100).toFixed(2)}`;
}

// Rounds only the bar's "far" end (away from the zero baseline) — square
// where it meets the baseline, per the mark spec.
function roundedRectPath(x, y, width, height, radius, roundedEdge) {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2));
  switch (roundedEdge) {
    case "top":
      return `M ${x} ${y + height} L ${x} ${y + r} Q ${x} ${y} ${x + r} ${y} L ${x + width - r} ${y} Q ${x + width} ${y} ${x + width} ${y + r} L ${x + width} ${y + height} Z`;
    case "bottom":
      return `M ${x} ${y} L ${x + width} ${y} L ${x + width} ${y + height - r} Q ${x + width} ${y + height} ${x + width - r} ${y + height} L ${x + r} ${y + height} Q ${x} ${y + height} ${x} ${y + height - r} Z`;
    case "right":
      return `M ${x} ${y} L ${x + width - r} ${y} Q ${x + width} ${y} ${x + width} ${y + r} L ${x + width} ${y + height - r} Q ${x + width} ${y + height} ${x + width - r} ${y + height} L ${x} ${y + height} Z`;
    case "left":
      return `M ${x + width} ${y} L ${x + r} ${y} Q ${x} ${y} ${x} ${y + r} L ${x} ${y + height - r} Q ${x} ${y + height} ${x + r} ${y + height} L ${x + width} ${y + height} Z`;
  }
}

// Rounds a raw magnitude up to a clean axis-tick number (100, 200, 500, 1000, ...).
function niceMax(value) {
  if (value <= 0) return 100;
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  const residual = value / magnitude;
  let niceResidual;
  if (residual <= 1) niceResidual = 1;
  else if (residual <= 2) niceResidual = 2;
  else if (residual <= 5) niceResidual = 5;
  else niceResidual = 10;
  return niceResidual * magnitude;
}

let tooltipEl;
function ensureTooltip() {
  if (!tooltipEl) {
    tooltipEl = document.createElement("div");
    tooltipEl.className = "tooltip";
    document.body.appendChild(tooltipEl);
  }
  return tooltipEl;
}

function showTooltip(evt, label, value) {
  const tt = ensureTooltip();
  tt.textContent = "";
  const valueSpan = document.createElement("span");
  valueSpan.className = "tt-value";
  valueSpan.textContent = value;
  const labelSpan = document.createElement("span");
  labelSpan.className = "tt-label";
  labelSpan.textContent = "  " + label;
  tt.appendChild(valueSpan);
  tt.appendChild(labelSpan);
  tt.style.left = evt.clientX + 12 + "px";
  tt.style.top = evt.clientY + 12 + "px";
  tt.classList.add("visible");
}

function hideTooltip() {
  if (tooltipEl) tooltipEl.classList.remove("visible");
}

function renderMonthChart(container, months, onSelect, selectedMonth) {
  container.textContent = "";
  if (months.length === 0) {
    container.innerHTML = '<p class="empty-state">No data yet.</p>';
    return;
  }

  const width = 900;
  const height = 280;
  const padding = { top: 16, right: 16, bottom: 32, left: 64 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  const values = months.map((m) => m.expenditure);
  const maxVal = Math.max(0, ...values);
  const minVal = Math.min(0, ...values);
  const axisMax = niceMax(Math.max(Math.abs(maxVal), Math.abs(minVal)));
  const rangeTop = maxVal > 0 ? axisMax : 0;
  const rangeBottom = minVal < 0 ? -axisMax : 0;
  const range = rangeTop - rangeBottom || 1;

  const scaleY = (value) => padding.top + ((rangeTop - value) / range) * plotHeight;

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "chart-svg",
    style: "width: 100%; height: auto;",
  });

  [rangeTop, 0, rangeBottom].forEach((gridVal, i) => {
    if (i > 0 && gridVal === 0 && rangeTop === 0) return;
    const y = scaleY(gridVal);
    svg.appendChild(
      el("line", {
        x1: padding.left,
        x2: width - padding.right,
        y1: y,
        y2: y,
        class: gridVal === 0 ? "baseline" : "gridline",
      })
    );
    const label = el("text", { x: padding.left - 8, y: y + 4, "text-anchor": "end", class: "axis-label" });
    label.textContent = formatMoney(gridVal);
    svg.appendChild(label);
  });

  const bandWidth = plotWidth / months.length;
  const barWidth = Math.min(24, bandWidth * 0.6);
  const zeroY = scaleY(0);

  months.forEach((m, i) => {
    const bandX = padding.left + i * bandWidth;
    const barX = bandX + (bandWidth - barWidth) / 2;
    const valueY = scaleY(m.expenditure);
    const barY = Math.min(zeroY, valueY);
    const barHeight = Math.max(1, Math.abs(valueY - zeroY));
    const roundedEdge = m.expenditure >= 0 ? "top" : "bottom";

    const bar = el("path", {
      d: roundedRectPath(barX, barY, barWidth, barHeight, 4, roundedEdge),
      class: "bar" + (m.month === selectedMonth ? " selected" : ""),
    });
    bar.addEventListener("click", () => onSelect(m.month));
    bar.addEventListener("pointermove", (evt) => showTooltip(evt, m.month, formatMoney(m.expenditure)));
    bar.addEventListener("pointerleave", hideTooltip);
    svg.appendChild(bar);

    const monthLabel = el("text", {
      x: bandX + bandWidth / 2,
      y: height - padding.bottom + 16,
      "text-anchor": "middle",
      class: "axis-label",
    });
    monthLabel.textContent = m.month.slice(5);
    svg.appendChild(monthLabel);
  });

  // Direct label only on the most recent month — selective, not one per bar.
  const last = months[months.length - 1];
  const lastX = padding.left + (months.length - 1) * bandWidth + bandWidth / 2;
  const lastY = scaleY(last.expenditure);
  const lastLabel = el("text", {
    x: lastX,
    y: last.expenditure >= 0 ? lastY - 8 : lastY + 16,
    "text-anchor": "middle",
    class: "value-label",
  });
  lastLabel.textContent = formatMoney(last.expenditure);
  svg.appendChild(lastLabel);

  container.appendChild(svg);
}

function renderCategoryChart(container, categories) {
  container.textContent = "";
  if (categories.length === 0) {
    container.innerHTML = '<p class="empty-state">No transactions.</p>';
    return;
  }

  const width = 900;
  const rowHeight = 32;
  const padding = { top: 8, right: 80, bottom: 8, left: 190 };
  const plotWidth = width - padding.left - padding.right;
  const height = padding.top + padding.bottom + categories.length * rowHeight;

  const values = categories.map((c) => c.total);
  const maxVal = Math.max(0, ...values);
  const minVal = Math.min(0, ...values);
  const axisMax = niceMax(Math.max(Math.abs(maxVal), Math.abs(minVal)));
  const rangeRight = maxVal > 0 ? axisMax : 0;
  const rangeLeft = minVal < 0 ? -axisMax : 0;
  const range = rangeRight - rangeLeft || 1;

  const scaleX = (value) => padding.left + ((value - rangeLeft) / range) * plotWidth;
  const zeroX = scaleX(0);

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "chart-svg",
    style: "width: 100%; height: auto;",
  });

  svg.appendChild(
    el("line", { x1: zeroX, x2: zeroX, y1: padding.top, y2: height - padding.bottom, class: "baseline" })
  );

  let extreme = categories[0];
  categories.forEach((c, i) => {
    const rowY = padding.top + i * rowHeight;
    const barHeight = Math.min(24, rowHeight * 0.6);
    const barY = rowY + (rowHeight - barHeight) / 2;
    const valueX = scaleX(c.total);
    const barX = Math.min(zeroX, valueX);
    const barWidth = Math.max(1, Math.abs(valueX - zeroX));
    const roundedEdge = c.total >= 0 ? "right" : "left";

    const bar = el("path", {
      d: roundedRectPath(barX, barY, barWidth, barHeight, 4, roundedEdge),
      class: "bar",
    });
    bar.addEventListener("pointermove", (evt) => showTooltip(evt, c.category, formatMoney(c.total)));
    bar.addEventListener("pointerleave", hideTooltip);
    svg.appendChild(bar);

    const catLabel = el("text", {
      x: padding.left - 8,
      y: rowY + rowHeight / 2 + 4,
      "text-anchor": "end",
      class: "axis-label",
    });
    catLabel.textContent = c.category;
    svg.appendChild(catLabel);

    if (Math.abs(c.total) > Math.abs(extreme.total)) extreme = c;
  });

  // Direct label only on the largest-magnitude category.
  const extremeIndex = categories.indexOf(extreme);
  const extremeRowY = padding.top + extremeIndex * rowHeight;
  const extremeValueX = scaleX(extreme.total);
  const extremeLabel = el("text", {
    x: extreme.total >= 0 ? extremeValueX + 6 : extremeValueX - 6,
    y: extremeRowY + rowHeight / 2 + 4,
    "text-anchor": extreme.total >= 0 ? "start" : "end",
    class: "value-label",
  });
  extremeLabel.textContent = formatMoney(extreme.total);
  svg.appendChild(extremeLabel);

  container.appendChild(svg);
}

function renderTransactionTable(container, transactions) {
  container.textContent = "";
  if (transactions.length === 0) {
    container.innerHTML = '<p class="empty-state">No transactions for this month.</p>';
    return;
  }

  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Date", "Amount", "Description", "Category"].forEach((text) => {
    const th = document.createElement("th");
    th.textContent = text;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  transactions.forEach((t) => {
    const tr = document.createElement("tr");

    const dateTd = document.createElement("td");
    dateTd.textContent = t.transaction_date;
    tr.appendChild(dateTd);

    const amountTd = document.createElement("td");
    amountTd.className = "amount";
    amountTd.textContent = formatMoney(t.amount);
    tr.appendChild(amountTd);

    const descTd = document.createElement("td");
    descTd.className = "desc";
    descTd.textContent = t.description;
    tr.appendChild(descTd);

    const catTd = document.createElement("td");
    catTd.textContent = t.category || "Uncategorized";
    tr.appendChild(catTd);

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

let allMonths = [];

async function selectMonth(month) {
  renderMonthChart(document.getElementById("month-chart"), allMonths, selectMonth, month);

  const summary = allMonths.find((m) => m.month === month);
  document.getElementById("hero-month").textContent = month;
  document.getElementById("hero-value").textContent = formatMoney(summary.expenditure);
  const separateEntries = Object.entries(summary.separate_totals || {});
  document.getElementById("hero-extra").textContent = separateEntries
    .map(([cat, total]) => `${cat}: ${formatMoney(total)}`)
    .join(", ");

  const [categories, transactions] = await Promise.all([
    fetchJSON(`/api/months/${month}/categories`),
    fetchJSON(`/api/months/${month}/transactions`),
  ]);
  renderCategoryChart(document.getElementById("category-chart"), categories);
  renderTransactionTable(document.getElementById("transaction-table"), transactions);
}

async function init() {
  allMonths = await fetchJSON("/api/months");
  if (allMonths.length === 0) {
    document.getElementById("month-chart").innerHTML =
      '<p class="empty-state">No data yet — run ingestion and categorization first.</p>';
    return;
  }
  await selectMonth(allMonths[allMonths.length - 1].month);
}

init();