/* Blast Furnace Simulator — front-end.
 * Everything (forms, tabs, results) is generated from the Python model's schema and
 * results, so new model sections appear here without changing this file. */
import { renderFurnace, CMAP_CSS } from "./furnace.js";

const $ = (s, r = document) => r.querySelector(s);
const STORAGE_KEY = "bf-sim-inputs-v1";
const WIDE_CHARTS = new Set(["sankey", "waterfall"]);

const state = {
  schema: null, defaults: {}, fields: {}, values: {}, out: null,
  tab: (location.hash || "#overview").slice(1), zone: "Stack", furnaceMode: "process",
  running: false, pending: false, live: true,
};

// ------------------------------------------------------------------ engine
const worker = new Worker("assets/js/worker.js");
let msgId = 0;
const waiting = new Map();
worker.onmessage = (e) => {
  const m = e.data;
  if (m.type === "progress") { setStatus("loading", m.text); $("#loading-text").textContent = m.text; return; }
  const p = waiting.get(m.id);
  if (!p) return;
  waiting.delete(m.id);
  m.ok ? p.resolve(m) : p.reject(new Error(m.error));
};
const call = (type, payload) => new Promise((resolve, reject) => {
  const id = ++msgId;
  waiting.set(id, { resolve, reject });
  worker.postMessage({ id, type, payload });
});

function setStatus(kind, text) {
  const s = $("#status");
  s.className = `status ${kind}`;
  s.querySelector(".txt").textContent = text;
}

async function runModel() {
  if (!state.schema) return;
  if (state.running) { state.pending = true; return; }
  state.running = true;
  setStatus("running", "Calculating…");
  $("#view").classList.add("stale");
  try {
    const m = await call("run", state.values);
    state.out = m.result;
    setStatus(Object.keys(state.out.errors).length ? "error" : "ready",
      Object.keys(state.out.errors).length ? "Finished with errors" : `Ready · ${Math.round(m.ms)} ms`);
    renderTabs();
    renderView();
  } catch (err) {
    setStatus("error", "Engine error");
    console.error(err);
    $("#view").innerHTML = `<div class="alert error">Model engine error: ${esc(err.message)}</div>`;
  } finally {
    $("#view").classList.remove("stale");
    state.running = false;
    if (state.pending) { state.pending = false; runModel(); }
  }
}
let debounce;
const scheduleRun = () => { if (!state.live) return; clearTimeout(debounce); debounce = setTimeout(runModel, 350); };

// ------------------------------------------------------------------ utils
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fmt(v) {
  if (typeof v !== "number") return esc(v ?? "");
  if (!isFinite(v)) return "–";
  const a = Math.abs(v);
  const d = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 10 ? 2 : a >= 1 ? 3 : 4;
  return v.toLocaleString("en-US", { maximumFractionDigits: d });
}
function download(name, text, type = "application/json") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
function mergeDeep(a, b) {
  const out = { ...a };
  for (const [k, v] of Object.entries(b || {})) {
    out[k] = v && typeof v === "object" && !Array.isArray(v) && typeof a[k] === "object" ? mergeDeep(a[k], v) : v;
  }
  return out;
}
const PLOT_BASE = {
  paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  font: { family: "Inter, sans-serif", color: "#c9cfda", size: 12 },
  margin: { l: 60, r: 20, t: 10, b: 50 },
  xaxis: { gridcolor: "#232a35", zerolinecolor: "#2f3744", linecolor: "#2f3744" },
  yaxis: { gridcolor: "#232a35", zerolinecolor: "#2f3744", linecolor: "#2f3744" },
  legend: { orientation: "h", y: -0.16, font: { size: 11 } },
  hoverlabel: { bgcolor: "#161b23", bordercolor: "#3a4352", font: { family: "JetBrains Mono", size: 12 } },
};

// ------------------------------------------------------------------ inputs
function buildInputs() {
  const host = $("#inputs");
  host.innerHTML = "";
  for (const sec of state.schema.sections) {
    if (!sec.inputs.length) continue;
    const lbl = document.createElement("div");
    lbl.className = "sec-label";
    lbl.textContent = sec.title;
    host.appendChild(lbl);
    for (const g of sec.inputs) {
      const det = document.createElement("details");
      det.className = "group";
      det.open = !g.collapsed;
      det.dataset.group = g.id;
      det.innerHTML = `<summary>${esc(g.title)}<span class="badge"></span></summary>${g.description ? `<p class="gdesc">${esc(g.description)}</p>` : ""}`;
      for (const f of g.fields) det.appendChild(buildField(f));
      host.appendChild(det);
    }
  }
  refreshChanged();
}

function buildField(f) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  wrap.dataset.key = f.key;
  wrap.dataset.search = `${f.label} ${f.key} ${f.help}`.toLowerCase();
  const id = `in-${f.key}`;
  wrap.innerHTML = `
    <div class="row">
      <label for="${id}" title="${esc(f.help || f.label)}">${esc(f.label)}</label>
      <div class="num">
        <button class="reset" title="Reset to default (${fmt(f.default)})">↺</button>
        <input type="number" id="${id}" step="${f.step ?? "any"}" ${f.min != null ? `min="${f.min}"` : ""} ${f.max != null ? `max="${f.max}"` : ""}>
        <span class="unit">${esc(f.unit)}</span>
      </div>
    </div>
    ${f.min != null && f.max != null ? `<input type="range" min="${f.min}" max="${f.max}" step="${f.step ?? "any"}" aria-label="${esc(f.label)}">` : ""}
    ${f.help ? `<div class="help">${esc(f.help)}</div>` : ""}`;
  const num = wrap.querySelector("input[type=number]");
  const rng = wrap.querySelector("input[type=range]");
  const set = (v, from) => {
    if (v === "" || isNaN(+v)) return;
    state.values[f.key] = +v;
    if (from !== num) num.value = +v;
    if (rng && from !== rng) rng.value = +v;
    wrap.classList.toggle("changed", +v !== f.default);
    refreshChanged();
    persist();
    scheduleRun();
  };
  num.value = state.values[f.key];
  if (rng) rng.value = state.values[f.key];
  wrap.classList.toggle("changed", state.values[f.key] !== f.default);
  num.addEventListener("input", () => set(num.value, num));
  num.addEventListener("change", () => { if (num.value === "") set(f.default); });
  rng && rng.addEventListener("input", () => set(rng.value, rng));
  wrap.querySelector(".reset").addEventListener("click", () => set(f.default));
  return wrap;
}

function refreshChanged() {
  const changed = Object.keys(state.values).filter((k) => state.values[k] !== state.defaults[k]);
  const info = $("#changed-info");
  info.innerHTML = changed.length
    ? `${changed.length} parameter${changed.length > 1 ? "s" : ""} changed from default · <button id="reset-all">reset all</button>`
    : "All parameters at default (reference furnace ≈ 6 000 tHM/day)";
  const r = $("#reset-all");
  r && r.addEventListener("click", resetAll);
  document.querySelectorAll(".group").forEach((g) => {
    const n = g.querySelectorAll(".field.changed").length;
    g.querySelector(".badge").textContent = n ? `${n} changed` : "";
  });
}
function persist() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state.values)); }
function applyValues(obj) {
  state.values = { ...state.defaults };
  for (const [k, v] of Object.entries(obj || {})) if (k in state.defaults && isFinite(+v)) state.values[k] = +v;
  persist();
  buildInputs();
  runModel();
}
function resetAll() { applyValues({}); }

$("#search").addEventListener("input", (e) => {
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll(".group").forEach((g) => {
    let any = false;
    g.querySelectorAll(".field").forEach((f) => {
      const hit = !q || f.dataset.search.includes(q);
      f.classList.toggle("hidden", !hit);
      any ||= hit;
    });
    g.style.display = any ? "" : "none";
    if (q && any) g.open = true;
  });
});

// ------------------------------------------------------------------ tabs
function renderTabs() {
  const tabs = [{ id: "overview", title: "Overview" }, ...state.schema.sections.map((s) => ({ id: s.id, title: s.title }))];
  if (!tabs.some((t) => t.id === state.tab)) state.tab = "overview";
  $("#tabs").innerHTML = tabs.map((t) => {
    const r = state.out?.results?.[t.id];
    const w = r?.warnings?.length ? `<span class="wcount">${r.warnings.length}</span>` : "";
    const e = r?.error ? `<span class="err">!</span>` : "";
    return `<button class="tab ${t.id === state.tab ? "active" : ""}" data-tab="${t.id}">${esc(t.title)}${w}${e}</button>`;
  }).join("");
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
    state.tab = b.dataset.tab;
    history.replaceState(null, "", `#${state.tab}`);
    renderTabs();
    renderView(true);
  }));
}

// ------------------------------------------------------------------ views
const chartDivs = new Map();       // keep Plotly divs alive across re-renders (smooth live updates)

function renderView(scrollTop = false) {
  if (!state.out) return;
  const y = window.scrollY;
  const view = $("#view");
  view.innerHTML = "";
  if (state.tab === "overview") renderOverview(view);
  else renderSection(view, state.schema.sections.find((s) => s.id === state.tab), state.out.results[state.tab]);
  window.scrollTo(0, scrollTop ? 0 : y);
}

function kpiHTML(k) {
  return `<div class="kpi ${k.status || ""}" ${k.section ? `data-goto="${k.section}"` : ""}>
    <div class="l">${esc(k.label)}</div>
    <div class="v">${fmt(k.value)}<span class="u">${esc(k.unit)}</span></div>
    ${k.hint ? `<div class="h">${esc(k.hint)}</div>` : ""}</div>`;
}

function equationHTML(eq) {
  let html = `<div class="card equation"><h3>${esc(eq.title)}</h3><div class="eq-row">`;
  let prevOut = false;
  eq.terms.forEach((t, i) => {
    const out = t.side === "out";
    if (i) html += `<div class="eq-op">${out && !prevOut ? "=" : "+"}</div>`;
    prevOut = out;
    const total = t.items.reduce((a, it) => a + (+it[1] || 0), 0);
    html += `<div class="eq-term ${out ? "out" : ""}"><div class="nm">${esc(t.name)}</div>
      <div class="val">${fmt(total)} <span class="u" style="font-size:12px;color:var(--muted)">${esc(eq.unit)}</span></div>
      <ul>${t.items.map((it) => `<li><span>${esc(it[0])}</span><span>${fmt(it[1])}</span></li>`).join("")}</ul></div>`;
  });
  const diff = eq.lhs_total ? (eq.lhs_total - eq.rhs_total) / eq.lhs_total * 100 : 0;
  html += `</div><div class="eq-check">Left side <b>${fmt(eq.lhs_total)}</b> ${esc(eq.unit)} · Right side <b>${fmt(eq.rhs_total)}</b> ${esc(eq.unit)} ·
    closure <b class="${Math.abs(diff) < 0.01 ? "ok" : ""}">${diff.toFixed(4)} %</b></div></div>`;
  return html;
}

function tableHTML(t, idx) {
  const isHead = (r) => r.slice(1).every((c) => c === "");
  const isTotal = (r) => /^total/i.test(String(r[0]));
  return `<div class="card ${t.columns.length > 6 ? "wide" : ""}">
    <div class="tbl-head"><h3>${esc(t.title)}</h3><button class="btn small" data-csv="${idx}">CSV</button></div>
    <div class="tbl-wrap"><table><thead><tr>${t.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${t.rows.map((r) => `<tr class="${isHead(r) ? "head" : isTotal(r) ? "total" : ""}">${r.map((c, i) =>
      `<td class="${typeof c === "number" && i ? "n" : ""}">${fmt(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    ${t.note ? `<div class="note">${esc(t.note)}</div>` : ""}</div>`;
}

function renderSection(view, sec, r) {
  if (!sec || !r) return;
  const alerts = [
    r.error ? `<div class="alert error"><b>This section failed:</b> ${esc(r.error)}<pre>${esc(r.trace || "")}</pre></div>` : "",
    ...(r.warnings || []).map((w) => `<div class="alert warn">⚠ ${esc(w)}</div>`),
  ].join("");
  view.innerHTML = `
    <div class="sec-head"><div><h2>${esc(sec.title)}</h2><p>${esc(sec.description)}</p></div></div>
    ${alerts ? `<div class="alerts">${alerts}</div>` : ""}
    ${(r.equations || []).map(equationHTML).join("")}
    ${r.kpis?.length ? `<div class="kpis">${r.kpis.map(kpiHTML).join("")}</div>` : ""}
    <div class="charts"></div>
    <div class="tables">${(r.tables || []).map(tableHTML).join("")}</div>`;
  const ch = $(".charts", view);
  for (const c of r.charts || []) {
    const card = document.createElement("div");
    card.className = "card" + (WIDE_CHARTS.has(c.id) ? " wide" : "");
    card.innerHTML = `<h3>${esc(c.title)}</h3>`;
    const key = `${sec.id}:${c.id}`;
    let div = chartDivs.get(key);
    if (!div) { div = document.createElement("div"); div.className = "plot"; chartDivs.set(key, div); }
    card.appendChild(div);
    if (c.note) card.insertAdjacentHTML("beforeend", `<div class="note">${esc(c.note)}</div>`);
    ch.appendChild(card);
    const layout = mergeDeep(PLOT_BASE, c.layout);
    if (c.data.some((d) => d.type === "pie" || d.type === "sankey")) { layout.margin = { l: 10, r: 10, t: 10, b: 10 }; }
    layout.autosize = true;
    if (window.Plotly) {
      Plotly.react(div, c.data, layout, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] })
        .then(() => requestAnimationFrame(() => div.isConnected && Plotly.Plots.resize(div)));
    }
  }
  if (!(r.charts || []).length) ch.remove();
  view.querySelectorAll("[data-csv]").forEach((b) => b.addEventListener("click", () => {
    const t = r.tables[+b.dataset.csv];
    const csv = [t.columns, ...t.rows].map((row) => row.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    download(`${sec.id}-${t.title.replace(/\W+/g, "_")}.csv`, csv, "text/csv");
  }));
}

function renderOverview(view) {
  const ov = state.out.overview;
  if (!ov) { view.innerHTML = `<div class="alert error">Overview unavailable: ${esc(JSON.stringify(state.out.errors))}</div>`; return; }
  const zones = ov.zone_info || [];
  if (!zones.some((z) => z.name === state.zone)) state.zone = zones[0]?.name;
  const z = zones.find((x) => x.name === state.zone);
  const warns = ov.warnings || [];
  view.innerHTML = `
    <div class="sec-head"><div><h2>Furnace Overview</h2>
      <p>Click a zone on the drawing to inspect temperatures and compositions. Hover inside the furnace for the local temperature.</p></div></div>
    <div class="overview">
      <div class="card furnace-card">
        <div class="furnace-toolbar"><span></span>
          <span class="seg"><button data-mode="process" class="${state.furnaceMode === "process" ? "on" : ""}">Process</button><button data-mode="thermal" class="${state.furnaceMode === "thermal" ? "on" : ""}">Isotherms</button></span>
        </div>
        <div id="furnace"></div>
        <div style="padding: 0 10px 10px">
          <div class="colorbar" style="background:${CMAP_CSS}"></div>
          <div class="colorbar-labels"><span>0 °C</span><span>500</span><span>1000</span><span>1500</span><span>2100 °C</span></div>
          <div class="legend" style="margin-top:10px">
            <span><i style="background:rgba(140,58,26,.9)"></i>Ore layer (sinter/pellet/lump)</span>
            <span><i style="background:#222"></i>Coke layer / active coke</span>
            <span><i style="background:rgba(150,60,20,.9);outline:1px dashed #7CFC9A"></i>Cohesive zone</span>
            <span><i style="background:#ffc04a"></i>Hot metal</span>
            <span><i style="background:#b88a2b"></i>Slag</span>
            <span><i style="background:#fff3a0"></i>Raceway</span>
          </div>
        </div>
      </div>
      <div class="side-stack">
        <div class="card zone-card">
          <div class="zone-pills">${zones.map((x) => `<button data-zone="${esc(x.name)}" class="${x.name === state.zone ? "on" : ""}">${esc(x.name)}</button>`).join("")}</div>
          ${z ? `<div class="zone-title"><h3>${esc(z.name)}</h3><span class="svg-sub">${z.z0.toFixed(1)}–${z.z1.toFixed(1)} m</span></div>
          <div class="zone-state">${esc(z.state)}</div>
          <div class="zone-items">${z.items.map((i) => `<div><div class="l">${esc(i[0])}</div><div class="v">${fmt(i[1])}<span class="u">${esc(i[2])}</span></div></div>`).join("")}</div>` : ""}
        </div>
        <div class="card"><h3>Key results</h3><div class="headline">${(ov.headline || []).map(kpiHTML).join("")}</div></div>
        ${warns.length ? `<div class="card"><h3>Model warnings (${warns.length})</h3><div class="alerts">${warns.map((w) =>
          `<div class="alert warn">⚠ ${esc(w.text)}</div>`).join("")}</div></div>` : ""}
      </div>
    </div>`;
  renderFurnace($("#furnace"), ov, {
    mode: state.furnaceMode, selected: state.zone, tBlast: state.values.t_blast,
    onSelect: (name) => { state.zone = name; renderView(); },
  });
  view.querySelectorAll("[data-zone]").forEach((b) => b.addEventListener("click", () => { state.zone = b.dataset.zone; renderView(); }));
  view.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => { state.furnaceMode = b.dataset.mode; renderView(); }));
  view.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => {
    state.tab = b.dataset.goto; history.replaceState(null, "", `#${state.tab}`); renderTabs(); renderView(true);
  }));
}

// ------------------------------------------------------------------ top bar actions
$("#btn-run").addEventListener("click", runModel);
$("#live").addEventListener("change", (e) => { state.live = e.target.checked; if (state.live) runModel(); });
$("#btn-menu").addEventListener("click", (e) => { e.stopPropagation(); $("#menu-list").classList.toggle("open"); });
document.addEventListener("click", () => $("#menu-list").classList.remove("open"));
$("#btn-inputs").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
$("#menu-list").addEventListener("click", (e) => {
  const act = e.target.dataset.act;
  if (act === "reset") resetAll();
  if (act === "export-inputs") download("blast-furnace-inputs.json", JSON.stringify(state.values, null, 2));
  if (act === "import-inputs") $("#file-input").click();
  if (act === "export-results" && state.out) download("blast-furnace-results.json", JSON.stringify(state.out, null, 1));
  if (act === "print") window.print();
});
$("#file-input").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try { applyValues(JSON.parse(await f.text())); } catch (err) { alert("Invalid JSON file: " + err.message); }
  e.target.value = "";
});
window.addEventListener("resize", () => { if (state.tab === "overview") return; chartDivs.forEach((d) => d.isConnected && window.Plotly && Plotly.Plots.resize(d)); });

// ------------------------------------------------------------------ boot
(async function boot() {
  const slow = setTimeout(() => {
    $("#loading-text").innerHTML = `Still loading… the Python runtime comes from a CDN (cdn.jsdelivr.net).
      If this takes more than a minute, <a href="" style="color:var(--accent)">reload the page</a>.`;
  }, 45000);
  try {
    const { result } = await call("init");
    clearTimeout(slow);
    state.schema = result.schema;
    for (const s of state.schema.sections) for (const g of s.inputs) for (const f of g.fields) {
      state.defaults[f.key] = f.default;
      state.fields[f.key] = f;
    }
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch (_) { /* ignore */ }
    state.values = { ...state.defaults };
    for (const [k, v] of Object.entries(saved)) if (k in state.defaults) state.values[k] = v;
    buildInputs();
    renderTabs();
    $("#btn-run").disabled = false;
    await runModel();
  } catch (err) {
    clearTimeout(slow);
    setStatus("error", "Failed to start");
    $("#loading-text").textContent = `Could not start the Python engine: ${err.message}. Check your internet connection (Pyodide is loaded from a CDN).`;
  }
})();
