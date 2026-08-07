const FULL_MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// Mirrors CATEGORY_GROUPS in categorization.py — used client-side to
// know which real categories roll up under a group label (e.g. "Train"
// is never itself a stored category, so filtering transactions by it
// means filtering by its members instead).
const CATEGORY_GROUPS = {
  Train: ["Subway", "Amtrak", "LIRR"],
};

// CATEGORY_GROUPS members aren't returned by GET /api/categories (never
// a real stored category — see CATEGORY_GROUPS above), but they're
// still valid reassignment targets, so they're added in explicitly.
const GROUP_MEMBER_CATEGORIES = Object.values(CATEGORY_GROUPS).flat();

// Okabe-Ito colorblind-safe qualitative palette. Color is decorative
// here, never load-bearing — the icon shape and the category name text
// both independently identify the category.
const ICONS = {
  "Eat Out": { color: "#E69F00", shape: '<rect x="5" y="4" width="10" height="9" rx="2"/><path d="M15 7h2a2 2 0 1 1 0 4h-2"/><line x1="5" y1="16" x2="15" y2="16"/>' },
  "Groceries": { color: "#56B4E9", shape: '<rect x="4" y="9" width="16" height="9" rx="1"/><line x1="4" y1="9" x2="8" y2="3"/><line x1="20" y1="9" x2="16" y2="3"/><line x1="4" y1="13" x2="20" y2="13"/>' },
  "Uber": { color: "#009E73", shape: '<rect x="3" y="10" width="18" height="6" rx="2"/><circle cx="7.5" cy="18" r="1.6"/><circle cx="16.5" cy="18" r="1.6"/>' },
  "Online purchases": { color: "#F0E442", shape: '<rect x="6" y="8" width="12" height="12" rx="1"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>' },
  "Medicines": { color: "#0072B2", shape: '<circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>' },
  "Miscellaneous": { color: "#D55E00", shape: '<circle cx="6" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="18" cy="12" r="1.4"/>' },
  "Train": { color: "#CC79A7", shape: '<rect x="5" y="4" width="14" height="12" rx="3"/><line x1="5" y1="11" x2="19" y2="11"/><circle cx="8.5" cy="19" r="1.4"/><circle cx="15.5" cy="19" r="1.4"/>' },
};
const FALLBACK_ICON = { color: "#8898aa", shape: '<rect x="5" y="4" width="14" height="16" rx="2"/><circle cx="9" cy="9" r="1.3"/>' };

function iconSvg(shape) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${shape}</svg>`;
}

// shape strings above are static constants written by us, never user
// data — safe to set via innerHTML. Everything derived from parsed
// statements or typed-in categories (description, category name) goes
// through textContent instead, never string-interpolated into markup.
function makeBadge(category, className) {
  const icon = ICONS[category] || FALLBACK_ICON;
  const badge = document.createElement("span");
  badge.className = className;
  badge.style.background = icon.color + "22";
  badge.style.color = icon.color;
  badge.innerHTML = iconSvg(icon.shape);
  badge.setAttribute("aria-hidden", "true");
  return badge;
}

// Magnitude only — for aggregate totals (KPI tiles, category bars),
// where "how much did I spend" should read as a plain positive number.
function formatMoney(cents) {
  return "$" + (Math.abs(cents) / 100).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Sign preserved — for individual transactions, where a credit/refund
// (positive) must stay visually distinct from a charge (negative). An
// aggregate category total can legitimately net out small even when the
// underlying transactions are large in both directions (a refund can
// outweigh the original charge) — this is what makes that visible.
function formatSignedMoney(cents) {
  const sign = cents < 0 ? "-" : "+";
  return sign + "$" + (Math.abs(cents) / 100).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function formatMonthFull(monthStr) {
  const [year, month] = monthStr.split("-");
  return `${FULL_MONTH_NAMES[parseInt(month, 10) - 1]} ${year}`;
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

async function patchJSON(url, body) {
  const res = await fetch(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

let allMonths = [];
let allCategories = [];
let monthCategories = [];
let monthTransactions = [];
let activeMonth = null;
let activeCategory = null;

let toastTimer;
function showToast(msg) {
  const toast = document.getElementById("toast");
  document.getElementById("toast-msg").textContent = msg;
  toast.classList.add("vis");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("vis"), 2400);
}

function renderSidebar() {
  const container = document.getElementById("sidebar-months");
  container.textContent = "";
  const sorted = [...allMonths].sort((a, b) => b.month.localeCompare(a.month));
  sorted.forEach((m) => {
    const item = document.createElement("div");
    item.className = "s-item" + (m.month === activeMonth ? " on" : "");
    item.textContent = formatMonthFull(m.month);
    item.addEventListener("click", () => selectMonth(m.month));
    container.appendChild(item);
  });
}

function renderKpis() {
  const idx = allMonths.findIndex((m) => m.month === activeMonth);
  const cur = allMonths[idx];

  document.getElementById("k-spend").textContent = formatMoney(cur.expenditure);

  const deltaEl = document.getElementById("k-delta");
  deltaEl.textContent = "";
  if (idx > 0 && Math.abs(allMonths[idx - 1].expenditure) > 0) {
    const prevMag = Math.abs(allMonths[idx - 1].expenditure);
    const curMag = Math.abs(cur.expenditure);
    const pct = Math.round(((curMag - prevMag) / prevMag) * 100);
    const span = document.createElement("span");
    span.className = pct >= 0 ? "up" : "down";
    span.textContent = (pct >= 0 ? "▲ " : "▼ ") + Math.abs(pct) + "%";
    deltaEl.appendChild(span);
    deltaEl.appendChild(document.createTextNode(" vs prior month"));
  } else {
    deltaEl.textContent = "First month tracked";
  }

  const separateEntries = Object.entries(cur.separate_totals || {});
  if (separateEntries.length > 0) {
    const extra = document.createElement("div");
    extra.className = "mono";
    extra.style.marginTop = "3px";
    extra.textContent = separateEntries.map(([cat, total]) => `${cat}: ${formatMoney(total)}`).join(", ");
    deltaEl.appendChild(extra);
  }

  document.getElementById("k-tx").textContent = monthTransactions.length;

  if (monthCategories.length > 0) {
    const top = monthCategories.reduce((a, b) => (Math.abs(a.total) > Math.abs(b.total) ? a : b));
    document.getElementById("k-top").textContent = top.category;
    document.getElementById("k-top-a").textContent = formatMoney(top.total);
  } else {
    document.getElementById("k-top").textContent = "—";
    document.getElementById("k-top-a").textContent = "—";
  }
}

function renderCategoryRow(c, max) {
  const row = document.createElement("div");
  row.className = "cat-row" + (c.category === activeCategory ? " on" : "");
  row.setAttribute("role", "row");
  const pct = max > 0 ? Math.round((Math.abs(c.total) / max) * 100) : 0;
  row.setAttribute("aria-label", `${c.category}, ${formatMoney(c.total)}, ${pct}% of the largest category`);

  row.appendChild(makeBadge(c.category, "cat-icon"));

  const name = document.createElement("div");
  name.className = "cat-name";
  name.textContent = c.category;
  row.appendChild(name);

  const barCell = document.createElement("div");
  barCell.className = "bar-cell";
  const track = document.createElement("div");
  track.className = "bar-track";
  track.setAttribute("role", "img");
  track.setAttribute("aria-label", `${pct}% of the largest category`);
  const inner = document.createElement("div");
  inner.className = "bar-inner";
  inner.style.width = pct + "%";
  track.appendChild(inner);
  barCell.appendChild(track);
  const pctLabel = document.createElement("span");
  pctLabel.className = "bar-pct";
  pctLabel.textContent = pct + "%";
  pctLabel.setAttribute("aria-hidden", "true");
  barCell.appendChild(pctLabel);
  row.appendChild(barCell);

  const amt = document.createElement("div");
  amt.className = "cat-amt mono";
  amt.textContent = formatMoney(c.total);
  row.appendChild(amt);

  row.addEventListener("click", () => selectCategory(c.category));
  return row;
}

function renderCategories() {
  const body = document.getElementById("cat-body");
  body.textContent = "";
  if (monthCategories.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No transactions.";
    body.appendChild(empty);
    return;
  }
  const max = Math.max(...monthCategories.map((c) => Math.abs(c.total)));
  monthCategories.forEach((c) => body.appendChild(renderCategoryRow(c, max)));
}

function transactionsForCategory(category) {
  const members = CATEGORY_GROUPS[category];
  if (members) return monthTransactions.filter((t) => members.includes(t.category));
  if (category === "Uncategorized") return monthTransactions.filter((t) => !t.category);
  return monthTransactions.filter((t) => t.category === category);
}

// Categories a transaction can be reassigned to: everything the server
// knows about (fixed list + anything ever actually assigned) plus
// CATEGORY_GROUPS members (valid targets, but never returned by
// /api/categories — see GROUP_MEMBER_CATEGORIES above), minus the
// current value.
function categoryOptions(current) {
  const set = new Set([...allCategories, ...GROUP_MEMBER_CATEGORIES]);
  set.delete(current);
  return [...set].sort();
}

function closeAllDropdowns() {
  document.querySelectorAll(".dd.vis").forEach((el) => el.classList.remove("vis"));
}

function makeCategoryPill(txn) {
  const wrap = document.createElement("div");
  wrap.style.position = "relative";

  const label = txn.category || "Uncategorized";

  const pill = document.createElement("span");
  pill.className = "pill";
  pill.setAttribute("role", "button");
  pill.setAttribute("tabindex", "0");
  pill.appendChild(makeBadge(label, "pill-badge"));
  const text = document.createElement("span");
  text.textContent = label;
  pill.appendChild(text);
  const chevron = document.createElement("span");
  chevron.textContent = "⌄";
  chevron.setAttribute("aria-hidden", "true");
  chevron.style.fontSize = "10px";
  pill.appendChild(chevron);

  const dd = document.createElement("div");
  dd.className = "dd";
  categoryOptions(txn.category).forEach((opt) => {
    const optEl = document.createElement("div");
    optEl.className = "dd-opt";
    optEl.appendChild(makeBadge(opt, "pill-badge"));
    const optText = document.createElement("span");
    optText.textContent = opt;
    optEl.appendChild(optText);
    optEl.addEventListener("click", (e) => {
      e.stopPropagation();
      reassign(txn, opt);
    });
    dd.appendChild(optEl);
  });

  pill.addEventListener("click", (e) => {
    e.stopPropagation();
    const wasOpen = dd.classList.contains("vis");
    closeAllDropdowns();
    if (!wasOpen) dd.classList.add("vis");
  });

  wrap.appendChild(pill);
  wrap.appendChild(dd);
  return wrap;
}

function renderTransactions(rows) {
  const body = document.getElementById("tx-body");
  body.textContent = "";

  if (rows.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No transactions.";
    body.appendChild(empty);
    return;
  }

  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Date", "Description", "Category", "Amount"].forEach((text) => {
    const th = document.createElement("th");
    th.textContent = text;
    if (text === "Amount") th.style.textAlign = "right";
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((t) => {
    const tr = document.createElement("tr");

    const dateTd = document.createElement("td");
    dateTd.className = "mono";
    dateTd.style.color = "var(--text3)";
    dateTd.textContent = t.transaction_date;
    tr.appendChild(dateTd);

    const descTd = document.createElement("td");
    descTd.className = "desc";
    descTd.textContent = t.description;
    tr.appendChild(descTd);

    const catTd = document.createElement("td");
    catTd.style.position = "relative";
    catTd.appendChild(makeCategoryPill(t));
    tr.appendChild(catTd);

    const amtTd = document.createElement("td");
    amtTd.className = "amount mono";
    amtTd.textContent = formatSignedMoney(t.amount);
    if (t.amount >= 0) amtTd.style.color = "var(--good)";
    tr.appendChild(amtTd);

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  body.appendChild(table);
}

// Signed + colored like formatSignedMoney's rationale: a group's members
// can individually net positive (a refund outweighing its charge) even
// though the group itself reads as routine spend — this is exactly the
// number that explains a group total that "doesn't add up" against the
// raw transaction list below it.
function renderSubgroupBreakdown(members) {
  const body = document.getElementById("subgroup-body");
  body.textContent = "";
  if (members.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No transactions.";
    body.appendChild(empty);
    return;
  }
  const max = Math.max(...members.map((m) => Math.abs(m.total)));
  members.forEach((m) => {
    const row = document.createElement("div");
    row.className = "cat-row";
    row.style.cursor = "default";
    row.appendChild(makeBadge(m.category, "cat-icon"));

    const name = document.createElement("div");
    name.className = "cat-name";
    name.textContent = m.category;
    row.appendChild(name);

    const barCell = document.createElement("div");
    barCell.className = "bar-cell";
    const track = document.createElement("div");
    track.className = "bar-track";
    const inner = document.createElement("div");
    inner.className = "bar-inner";
    const pct = max > 0 ? Math.round((Math.abs(m.total) / max) * 100) : 0;
    inner.style.width = pct + "%";
    track.appendChild(inner);
    barCell.appendChild(track);
    const pctLabel = document.createElement("span");
    pctLabel.className = "bar-pct";
    pctLabel.textContent = pct + "%";
    barCell.appendChild(pctLabel);
    row.appendChild(barCell);

    const amt = document.createElement("div");
    amt.className = "cat-amt mono";
    amt.textContent = formatSignedMoney(m.total);
    if (m.total >= 0) amt.style.color = "var(--good)";
    row.appendChild(amt);

    body.appendChild(row);
  });
}

async function selectCategory(category) {
  activeCategory = category;
  renderCategories();

  const subgroupCard = document.getElementById("subgroup-card");
  const members = CATEGORY_GROUPS[category];
  if (members) {
    const memberTotals = await fetchJSON(`/api/months/${activeMonth}/categories/${encodeURIComponent(category)}`);
    document.getElementById("subgroup-title").textContent = `${category} breakdown`;
    renderSubgroupBreakdown(memberTotals);
    subgroupCard.style.display = "block";
  } else {
    subgroupCard.style.display = "none";
  }

  document.getElementById("tx-title").textContent = `${category} — transactions`;
  document.getElementById("tx-card").style.display = "block";
  renderTransactions(transactionsForCategory(category));
  document.getElementById("tx-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function reassign(txn, newCategory) {
  closeAllDropdowns();
  try {
    await patchJSON(`/api/transactions/${txn.id}`, { category: newCategory });
  } catch (err) {
    showToast("Couldn't update — try again");
    return;
  }
  showToast(`Moved "${txn.description}" to ${newCategory}`);

  const [categories, transactions] = await Promise.all([
    fetchJSON(`/api/months/${activeMonth}/categories`),
    fetchJSON(`/api/months/${activeMonth}/transactions`),
  ]);
  monthCategories = categories;
  monthTransactions = transactions;
  renderKpis();
  renderCategories();
  if (activeCategory) renderTransactions(transactionsForCategory(activeCategory));
}

document.addEventListener("click", closeAllDropdowns);

async function selectMonth(month) {
  activeMonth = month;
  activeCategory = null;
  renderSidebar();
  document.getElementById("tx-card").style.display = "none";
  document.getElementById("subgroup-card").style.display = "none";
  document.getElementById("cat-title").textContent = `Categories — ${formatMonthFull(month)}`;

  const [categories, transactions] = await Promise.all([
    fetchJSON(`/api/months/${month}/categories`),
    fetchJSON(`/api/months/${month}/transactions`),
  ]);
  monthCategories = categories;
  monthTransactions = transactions;
  renderKpis();
  renderCategories();
}

function systemPrefersDark() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function isDarkActive() {
  if (document.body.classList.contains("dark")) return true;
  if (document.body.classList.contains("light")) return false;
  return systemPrefersDark();
}

function updateDarkModeLabel() {
  document.getElementById("dm-btn").textContent = isDarkActive() ? "Light mode" : "Dark mode";
}

function toggleDarkMode() {
  const goingDark = !isDarkActive();
  document.body.classList.remove("dark", "light");
  document.body.classList.add(goingDark ? "dark" : "light");
  localStorage.setItem("expense-analyser-theme", goingDark ? "dark" : "light");
  updateDarkModeLabel();
}

function initDarkMode() {
  const saved = localStorage.getItem("expense-analyser-theme");
  if (saved === "dark" || saved === "light") document.body.classList.add(saved);
  updateDarkModeLabel();
  document.getElementById("dm-btn").addEventListener("click", toggleDarkMode);
}

async function init() {
  initDarkMode();
  [allMonths, allCategories] = await Promise.all([fetchJSON("/api/months"), fetchJSON("/api/categories")]);
  if (allMonths.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No data yet — run ingestion and categorization first.";
    document.getElementById("cat-body").appendChild(empty);
    return;
  }
  const latest = [...allMonths].sort((a, b) => b.month.localeCompare(a.month))[0];
  await selectMonth(latest.month);
}

init();
