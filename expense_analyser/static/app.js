const SVG_NS = "http://www.w3.org/2000/svg";
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function el(tag, attrs = {}) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) e.setAttribute(key, value);
  return e;
}

function formatMoney(cents) {
  const sign = cents < 0 ? "-" : "";
  return `${sign}$${(Math.abs(cents) / 100).toFixed(2)}`;
}

// "2026-01" -> "Jan '26" (year included since data can span a year boundary)
function formatMonthLabel(monthStr) {
  const [year, month] = monthStr.split("-");
  const monthIndex = parseInt(month, 10) - 1;
  return `${MONTH_NAMES[monthIndex]} '${year.slice(2)}`;
}

// Rounds only the bar's "far" end (away from the baseline) — square
// where it meets the baseline, per the mark spec.
function roundedRectPath(x, y, width, height, radius, roundedEdge) {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2));
  switch (roundedEdge) {
    case "top":
      return `M ${x} ${y + height} L ${x} ${y + r} Q ${x} ${y} ${x + r} ${y} L ${x + width - r} ${y} Q ${x + width} ${y} ${x + width} ${y + r} L ${x + width} ${y + height} Z`;
    case "right":
      return `M ${x} ${y} L ${x + width - r} ${y} Q ${x + width} ${y} ${x + width} ${y + r} L ${x + width} ${y + height - r} Q ${x + width} ${y + height} ${x + width - r} ${y + height} L ${x} ${y + height} Z`;
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

// Both charts plot Math.abs(cents) — spend is stored as negative but
// should just read as a positive amount. One baseline, one rounded
// edge per bar (no zero-crossing to worry about).

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

  const magnitudes = months.map((m) => Math.abs(m.expenditure));
  const axisMax = niceMax(Math.max(...magnitudes, 0));

  const scaleY = (value) => padding.top + (1 - value / axisMax) * plotHeight;
  const baselineY = scaleY(0);

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "chart-svg",
    style: "width: 100%; height: auto;",
  });

  [axisMax, axisMax / 2, 0].forEach((gridVal) => {
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

  months.forEach((m, i) => {
    const magnitude = Math.abs(m.expenditure);
    const bandX = padding.left + i * bandWidth;
    const barX = bandX + (bandWidth - barWidth) / 2;
    const barTopY = scaleY(magnitude);
    const barHeight = Math.max(1, baselineY - barTopY);

    const bar = el("path", {
      d: roundedRectPath(barX, barTopY, barWidth, barHeight, 4, "top"),
      class: "bar" + (m.month === selectedMonth ? " selected" : ""),
    });
    bar.addEventListener("click", () => onSelect(m.month));
    bar.addEventListener("pointermove", (evt) => showTooltip(evt, formatMonthLabel(m.month), formatMoney(magnitude)));
    bar.addEventListener("pointerleave", hideTooltip);
    svg.appendChild(bar);

    const monthLabel = el("text", {
      x: bandX + bandWidth / 2,
      y: height - padding.bottom + 16,
      "text-anchor": "middle",
      class: "axis-label",
    });
    monthLabel.textContent = formatMonthLabel(m.month);
    svg.appendChild(monthLabel);

    const valueLabel = el("text", {
      x: bandX + bandWidth / 2,
      y: barTopY - 8,
      "text-anchor": "middle",
      class: "value-label",
    });
    valueLabel.textContent = formatMoney(magnitude);
    svg.appendChild(valueLabel);
  });

  container.appendChild(svg);
}

function renderCategoryChart(container, categories, onBarClick) {
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

  const magnitudes = categories.map((c) => Math.abs(c.total));
  const axisMax = niceMax(Math.max(...magnitudes, 0));

  const scaleX = (value) => padding.left + (value / axisMax) * plotWidth;

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "chart-svg",
    style: "width: 100%; height: auto;",
  });

  svg.appendChild(
    el("line", { x1: padding.left, x2: padding.left, y1: padding.top, y2: height - padding.bottom, class: "baseline" })
  );

  categories.forEach((c, i) => {
    const magnitude = Math.abs(c.total);
    const rowY = padding.top + i * rowHeight;
    const barHeight = Math.min(24, rowHeight * 0.6);
    const barY = rowY + (rowHeight - barHeight) / 2;
    const barWidth = Math.max(1, scaleX(magnitude) - padding.left);

    const bar = el("path", {
      d: roundedRectPath(padding.left, barY, barWidth, barHeight, 4, "right"),
      class: "bar",
    });
    bar.addEventListener("pointermove", (evt) => showTooltip(evt, c.category, formatMoney(magnitude)));
    bar.addEventListener("pointerleave", hideTooltip);
    if (onBarClick) bar.addEventListener("click", () => onBarClick(c.category));
    svg.appendChild(bar);

    const catLabel = el("text", {
      x: padding.left - 8,
      y: rowY + rowHeight / 2 + 4,
      "text-anchor": "end",
      class: "axis-label",
    });
    catLabel.textContent = c.category;
    svg.appendChild(catLabel);

    const valueLabel = el("text", {
      x: scaleX(magnitude) + 6,
      y: rowY + rowHeight / 2 + 4,
      "text-anchor": "start",
      class: "value-label",
    });
    valueLabel.textContent = formatMoney(magnitude);
    svg.appendChild(valueLabel);
  });

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

// .../categories/{name} comes back empty for a non-group category, so
// this same handler works on every bar without knowing in advance
// which ones are groups.
async function showGroupBreakdown(month, category) {
  const card = document.getElementById("subcategory-card");
  const members = await fetchJSON(`/api/months/${month}/categories/${encodeURIComponent(category)}`);

  if (members.length === 0) {
    card.hidden = true;
    return;
  }

  card.hidden = false;
  document.getElementById("subcategory-heading").textContent = `${category} breakdown`;
  renderCategoryChart(document.getElementById("subcategory-chart"), members);
}

async function selectMonth(month) {
  renderMonthChart(document.getElementById("month-chart"), allMonths, selectMonth, month);

  const summary = allMonths.find((m) => m.month === month);
  document.getElementById("hero-month").textContent = formatMonthLabel(month);
  document.getElementById("hero-value").textContent = formatMoney(Math.abs(summary.expenditure));
  const separateEntries = Object.entries(summary.separate_totals || {});
  document.getElementById("hero-extra").textContent = separateEntries
    .map(([cat, total]) => `${cat}: ${formatMoney(Math.abs(total))}`)
    .join(", ");

  document.getElementById("subcategory-card").hidden = true; // stale for the old month

  const [categories, transactions] = await Promise.all([
    fetchJSON(`/api/months/${month}/categories`),
    fetchJSON(`/api/months/${month}/transactions`),
  ]);
  // Income/Stony Brook already excluded server-side — still visible in the hero figure above.
  renderCategoryChart(document.getElementById("category-chart"), categories, (category) =>
    showGroupBreakdown(month, category)
  );
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