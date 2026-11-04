// Radar Bursátil: web estática. Lee docs/data/*.json (que genera la revisión diaria en GitHub Actions).
import { suggest } from "./rotation.js";

const DEFAULT_MODEL = "claude-sonnet-5-5";
const LS = { key: "radar.claveAnthropic", github: "radar.tokenGithub", amount: "radar.aporte" };
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const VEREDICTOS = { reforzar: "Reforzar", mantener: "Mantener", vigilar: "Vigilar", salir: "Salir", evitar: "Evitar" };

const LINKS = [
  ["Bolsas de América", [
    ["NYSE", "Bolsa de Nueva York", "https://www.nyse.com"],
    ["Nasdaq", "Cotizaciones y mercado Nasdaq", "https://www.nasdaq.com/market-activity"],
    ["BYMA", "Bolsas y Mercados Argentinos", "https://www.byma.com.ar"],
    ["B3", "Bolsa de Brasil", "https://www.b3.com.br"],
    ["BMV", "Bolsa Mexicana de Valores", "https://www.bmv.com.mx"],
    ["TSX", "Bolsa de Toronto", "https://www.tsx.com"],
  ]],
  ["Bolsas de Europa", [
    ["London Stock Exchange", "Bolsa de Londres", "https://www.londonstockexchange.com"],
    ["Euronext", "París, Ámsterdam, Milán y más", "https://www.euronext.com"],
    ["Börse Frankfurt", "Bolsa de Frankfurt (Xetra)", "https://www.boerse-frankfurt.de"],
    ["SIX Swiss Exchange", "Bolsa de Suiza", "https://www.six-group.com"],
  ]],
  ["Bolsas de Asia", [
    ["Japan Exchange Group", "Bolsa de Tokio", "https://www.jpx.co.jp/english/"],
    ["HKEX", "Bolsa de Hong Kong", "https://www.hkex.com.hk"],
    ["Shanghai Stock Exchange", "Bolsa de Shanghái", "https://english.sse.com.cn"],
    ["NSE India", "Bolsa Nacional de la India", "https://www.nseindia.com"],
  ]],
  ["Información y noticias", [
    ["Yahoo Finanzas", "Cotizaciones, gráficos y balances", "https://finance.yahoo.com"],
    ["Investing.com", "Mercados globales en español", "https://es.investing.com"],
    ["Bloomberg", "Mercados y noticias", "https://www.bloomberg.com/markets"],
    ["Reuters", "Noticias de mercados", "https://www.reuters.com/markets/"],
    ["Financial Times", "Mercados", "https://www.ft.com/markets"],
    ["CNBC", "Mercados", "https://www.cnbc.com/markets/"],
    ["MarketWatch", "Cotizaciones y noticias", "https://www.marketwatch.com"],
    ["TradingView", "Gráficos y análisis técnico", "https://www.tradingview.com/markets/"],
    ["SEC EDGAR", "Balances oficiales de empresas de EE.UU.", "https://www.sec.gov/edgar/search/"],
  ]],
  ["Argentina", [
    ["Rava Bursátil", "Acciones, bonos y CEDEARs", "https://www.rava.com"],
    ["Ámbito", "Finanzas y dólar", "https://www.ambito.com"],
    ["El Cronista", "Finanzas y mercados", "https://www.cronista.com/finanzas-mercados/"],
    ["BCRA", "Banco Central de la República Argentina", "https://www.bcra.gob.ar"],
    ["CNV", "Comisión Nacional de Valores", "https://www.argentina.gob.ar/cnv"],
  ]],
  ["Bonos, tasas y datos", [
    ["Tasas del Tesoro de EE.UU.", "Curva oficial de rendimientos", "https://home.treasury.gov/resource-center/data-chart-center/interest-rates"],
    ["FRED", "Datos económicos de la Reserva Federal de St. Louis", "https://fred.stlouisfed.org"],
    ["Google Patents", "Buscador de patentes", "https://patents.google.com"],
  ]],
];

const state = { meta: null, plan: null, ideas: null, ai: null, signals: null, markets: null, prompt: null, filter: "todas", busy: false };

// ---------- utilidades ----------
const $ = (s, root = document) => root.querySelector(s);
const nf = (d) => new Intl.NumberFormat("es-AR", { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test(String(u || "")) ? String(u) : "#");
const lsGet = (k) => { try { return localStorage.getItem(k) || ""; } catch { return ""; } };
const lsSet = (k, v) => { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch { /* sin almacenamiento */ } };
const pct = (v, { signed = false, d = 1 } = {}) => (v == null || Number.isNaN(Number(v)) ? "—" : `${signed && v > 0 ? "+" : ""}${nf(d).format(v)} %`);
const money = (v, d = 0) => (v == null ? "—" : `US$ ${nf(d).format(v)}`);
const price = (v) => (v == null ? "—" : nf(Math.abs(v) < 1 ? 4 : 2).format(v));
const trend = (v) => (v == null || v === 0 ? "flat" : v > 0 ? "up" : "down");
const yahoo = (t) => `https://finance.yahoo.com/quote/${encodeURIComponent(t)}`;
const inlineMd = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
const parseNum = (s) => { const n = parseFloat(String(s).replace(/\s/g, "").replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", ".")); return Number.isFinite(n) ? n : NaN; };
function when(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("es-AR", { weekday: "short", day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
}
function spark(values, cls) {
  if (!values || values.length < 2) return '<svg class="spark" aria-hidden="true"></svg>';
  const w = 96, h = 32, p = 2;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const pts = values.map((v, i) => `${(p + (i / (values.length - 1)) * (w - 2 * p)).toFixed(1)},${(h - p - ((v - min) / span) * (h - 2 * p)).toFixed(1)}`).join(" ");
  return `<svg class="spark ${cls}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}
async function loadJson(name) {
  try { const r = await fetch(`data/${name}?t=${Date.now()}`, { cache: "no-store" }); return r.ok ? await r.json() : null; } catch { return null; }
}
function setStatus(el, html, kind = "") { el.className = `status ${kind}`; el.innerHTML = html; }
const working = (msg) => `${esc(msg)}<div class="bar"><i></i></div>`;
const tesisBy = () => new Map(((state.ai?.revision?.tesis) || []).map((t) => [t.ticker, t]));

// ---------- navegación ----------
const TABS = ["plan", "ideas", "senales", "mercados", "enlaces", "ayuda"];
function route() {
  const tab = TABS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "plan";
  for (const t of TABS) {
    $(`#tab-${t}`).hidden = t !== tab;
    const a = $(`.tabs a[data-tab="${t}"]`);
    if (t === tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
}

// ---------- aporte del mes ----------
function holdingValues() {
  const out = {};
  for (const h of state.plan?.cartera || []) if (h.valor_usd != null) out[h.ticker] = h.valor_usd;
  return out;
}

function renderSuggestion() {
  const list = $("#suggestion");
  const p = state.plan;
  if (!p) { list.innerHTML = '<li class="empty">Todavía no hay datos. Aparecen después de la primera revisión diaria en GitHub.</li>'; return; }
  const amount = parseNum($("#amount").value);
  if (!(amount >= 1)) { list.innerHTML = '<li class="empty">Escribí un monto en dólares.</li>'; return; }
  const items = suggest(p.grupos, holdingValues(), amount, p.ranking || {}, p.senales || {});
  if (!items.length) { list.innerHTML = '<li class="empty">No hay instrumentos disponibles para sugerir. Revisá la distribución en config.json.</li>'; return; }
  const tb = tesisBy();
  const first = !(p.cartera || []).length;
  list.innerHTML = items.map((s) => {
    const name = p.nombres?.[s.ticker] || "";
    const why = first
      ? `${esc(s.nombre_grupo)} es el grupo con más peso en tu plan (${pct(s.objetivo_pct, { d: 0 })}). Se empieza por ahí.`
      : s.actual_pct < s.objetivo_pct
        ? `${esc(s.nombre_grupo)} está en ${pct(s.actual_pct, { d: 0 })} de tu cartera y el objetivo es ${pct(s.objetivo_pct, { d: 0 })}.`
        : `Con este aporte tu cartera crece y a ${esc(s.nombre_grupo)} le faltan ${money(s.falta_usd)} para sostener su ${pct(s.objetivo_pct, { d: 0 })}.`;
    const extra = [];
    if (s.grupo !== "Núcleo" && s.puntaje != null) extra.push(`Mejor puntaje del grupo: ${nf(0).format(s.puntaje)} de 100.`);
    if (s.senal === "VENTA" && s.grupo === "Núcleo") extra.push("Tiene señal técnica de venta, pero en el núcleo a largo plazo se mantiene el aporte.");
    const t = tb.get(s.ticker);
    if (t) extra.push(`IA: ${VEREDICTOS[t.veredicto] || t.veredicto}.`);
    return `<li class="pick">
      <div class="pick-main"><span class="pick-ticker">${esc(s.ticker)}</span><span class="pick-amount">${money(s.monto_usd)}</span></div>
      <p class="pick-name">${esc(name)}${s.grupo ? ` · ${esc(s.grupo)}` : ""}</p>
      <p class="pick-why">${why} ${esc(extra.join(" "))}</p>
      <button class="btn small" type="button" data-register="${esc(s.ticker)}" data-amount="${s.monto_usd}">Registrar esta compra</button>
    </li>`;
  }).join("");
  list.querySelectorAll("[data-register]").forEach((b) => b.addEventListener("click", () => prefillRegister(b.dataset.register, b.dataset.amount)));
}

function renderAiOnContribution() {
  const a = state.ai?.revision?.aporte;
  const el = $("#ai-on-contribution");
  if (a?.comentario) el.innerHTML = `<b>${a.de_acuerdo === false ? "La IA sugiere otra cosa este mes:" : "La IA está de acuerdo:"}</b> ${inlineMd(a.comentario)} <span class="muted">(revisión del ${esc(when(state.ai.creada))}, calculada para tu aporte habitual)</span>`;
  else el.textContent = "";
}

// ---------- plan vs. real ----------
function renderSleeves() {
  const p = state.plan;
  const root = $("#sleeves");
  if (!p) { root.innerHTML = ""; $("#vs-lead").textContent = ""; return; }
  const has = (p.total_usd || 0) > 0;
  $("#vs-lead").textContent = has
    ? "La barra es lo que tenés hoy; la línea dorada, tu objetivo. Los aportes van llenando lo que está más lejos de la línea."
    : "Así se va a repartir tu cartera. Cuando registres compras vas a ver cuánto llevás de cada parte.";
  const groups = new Map();
  for (const g of p.grupos) { if (!groups.has(g.grupo)) groups.set(g.grupo, []); groups.get(g.grupo).push(g); }
  const max = Math.max(50, ...p.grupos.map((g) => Math.max(g.peso, g.actual_pct))) * 1.05;
  root.innerHTML = [...groups.entries()].map(([grupo, gs]) => {
    const target = gs.reduce((s, g) => s + g.peso, 0), actual = gs.reduce((s, g) => s + g.actual_pct, 0);
    return `<div class="sleeve-group"><h3>${esc(grupo)} <span class="muted">${has ? `${pct(actual, { d: 0 })} de ` : ""}${pct(target, { d: 0 })} objetivo</span></h3>
      ${gs.map((g) => `<div class="sleeve">
        <div class="sleeve-label"><span>${esc(g.nombre)}</span><span class="muted">${esc(g.candidatos.join(", "))}</span></div>
        <div class="sleeve-bar" role="img" aria-label="${esc(g.nombre)}: ${pct(g.actual_pct, { d: 0 })} hoy, objetivo ${pct(g.peso, { d: 0 })}">
          <span class="fill ${g.actual_pct > g.peso + 2 ? "over" : ""}" style="width:${(g.actual_pct / max) * 100}%"></span>
          <span class="target" style="left:${(g.peso / max) * 100}%"></span>
        </div>
        <div class="sleeve-nums">${has ? `<b>${pct(g.actual_pct, { d: 0 })}</b> / ` : ""}${pct(g.peso, { d: 0 })}</div>
      </div>`).join("")}</div>`;
  }).join("");
}

function renderHoldings() {
  const p = state.plan;
  const root = $("#holdings");
  if (!p || !(p.cartera || []).length) {
    root.innerHTML = '<p class="empty">Todavía no registraste compras. Cuando hagas tu primer aporte, anotalo más abajo.</p>';
    return;
  }
  const total = p.total_usd || 0;
  root.innerHTML = `
    <div class="totals">
      <div><span class="muted">Vale hoy</span><b>${money(p.total_usd, 2)}</b></div>
      <div><span class="muted">Invertiste</span><b>${money(p.invertido_usd, 2)}</b></div>
      <div><span class="muted">Resultado</span><b class="${trend(p.resultado_usd)}">${money(p.resultado_usd, 2)} (${pct(p.resultado_pct, { signed: true })})</b></div>
    </div>
    <div class="table-wrap"><table class="table">
      <thead><tr><th scope="col">Instrumento</th><th scope="col">Peso</th><th scope="col">Vale hoy</th><th scope="col" class="hide-sm">Invertido</th><th scope="col">Resultado</th></tr></thead>
      <tbody>${p.cartera.map((h) => `<tr>
        <th scope="row"><a href="${yahoo(h.ticker)}" target="_blank" rel="noopener">${esc(h.ticker)}</a></th>
        <td>${total ? pct(((h.valor_usd || 0) / total) * 100, { d: 0 }) : "—"}</td>
        <td>${money(h.valor_usd, 2)}</td>
        <td class="hide-sm">${money(h.invertido_usd, 2)}</td>
        <td class="${trend(h.resultado_usd)}">${pct(h.resultado_pct, { signed: true })}</td>
      </tr>`).join("")}</tbody>
    </table></div>`;
}

// ---------- registrar compras ----------
function prefillRegister(ticker, amount) {
  const f = $("#register-form");
  f.ticker.value = ticker;
  if (amount) f.monto.value = amount;
  fillPrice();
  $("#register").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  f.monto.focus({ preventScroll: true });
}
function fillPrice() {
  const f = $("#register-form");
  const t = f.ticker.value.trim().toUpperCase();
  const pr = state.plan?.precios?.[t];
  if (pr) f.precio.value = nf(2).format(pr).replace(/\./g, "");
}

const b64ToUtf8 = (s) => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\n/g, "")), (c) => c.charCodeAt(0)));
const utf8ToB64 = (s) => { let bin = ""; new TextEncoder().encode(s).forEach((b) => { bin += String.fromCharCode(b); }); return btoa(bin); };

async function register(e) {
  e.preventDefault();
  if (state.busy) return;
  const f = e.target;
  const status = $("#register-status");
  const mov = {
    fecha: f.fecha.value,
    ticker: f.ticker.value.trim().toUpperCase(),
    tipo: f.tipo.value,
    monto_usd: parseNum(f.monto.value),
    precio_usd: parseNum(f.precio.value),
  };
  if (f.nota.value.trim()) mov.nota = f.nota.value.trim();
  if (!mov.fecha || !mov.ticker || !(mov.monto_usd > 0) || !(mov.precio_usd > 0)) {
    setStatus(status, "Completá fecha, instrumento, monto y precio (mayores a cero).", "error");
    return;
  }
  const repo = state.meta?.repositorio;
  const token = lsGet(LS.github);
  const snippet = esc(JSON.stringify(mov));
  if (!repo || !token) {
    setStatus(status, `Para guardar con un botón, cargá un token de GitHub en <a href="#ayuda">Ayuda</a>. Si no, abrí ${repo ? `<a href="https://github.com/${esc(repo)}/edit/main/cartera.json" target="_blank" rel="noopener">cartera.json en GitHub</a>` : "cartera.json en GitHub"} y agregá esta línea dentro de "movimientos" (separada por una coma de la anterior):<pre class="snippet">${snippet}</pre>`);
    return;
  }
  const gh = (path, opts = {}) => fetch(`https://api.github.com/repos/${repo}${path}`, {
    ...opts, headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", ...(opts.headers || {}) },
  });
  state.busy = true; $("#register-btn").disabled = true;
  setStatus(status, working("Guardando en tu cartera…"));
  try {
    const info = await gh("");
    if (!info.ok) throw new Error(info.status === 401 ? "El token de GitHub no es válido." : `GitHub respondió ${info.status}.`);
    const branch = (await info.json()).default_branch || "main";
    const cur = await gh(`/contents/cartera.json?ref=${encodeURIComponent(branch)}`);
    let sha, doc = { movimientos: [] };
    if (cur.ok) { const file = await cur.json(); sha = file.sha; doc = JSON.parse(b64ToUtf8(file.content)); }
    else if (cur.status !== 404) throw new Error(`No pude leer cartera.json (GitHub respondió ${cur.status}).`);
    doc.movimientos = [...(doc.movimientos || []), mov];
    const put = await gh("/contents/cartera.json", {
      method: "PUT",
      body: JSON.stringify({ message: `Registro ${mov.tipo} de ${mov.ticker}`, content: utf8ToB64(`${JSON.stringify(doc, null, 2)}\n`), sha, branch }),
    });
    if (!put.ok) throw new Error(`No pude guardar (GitHub respondió ${put.status}). Revisá que el token tenga permiso de escritura sobre el contenido.`);
    const run = await gh("/actions/workflows/actualizar.yml/dispatches", { method: "POST", body: JSON.stringify({ ref: branch }) });
    setStatus(status, run.ok
      ? `Guardado: ${esc(mov.tipo)} de ${esc(mov.ticker)} por ${money(mov.monto_usd, 2)}. La página se actualiza en unos minutos.`
      : `Guardado: ${esc(mov.tipo)} de ${esc(mov.ticker)}. Se va a ver en la próxima revisión diaria.`);
    f.monto.value = ""; f.nota.value = "";
  } catch (err) {
    setStatus(status, esc(err.message), "error");
  } finally {
    state.busy = false; $("#register-btn").disabled = false;
  }
}

// ---------- revisión de la IA ----------
function renderAiReview() {
  const root = $("#ai-review");
  const r = state.ai?.revision;
  if (!r) {
    root.innerHTML = `<h2 id="h-ia">Revisión mensual con IA</h2><p class="muted">${esc(state.meta?.ia || "Opcional. Sin la clave de la IA, el plan funciona igual y gratis.")}</p>`;
    return;
  }
  const list = (title, items) => (items?.length ? `<h3>${title}</h3><ul>${items.map((x) => `<li>${inlineMd(x)}</li>`).join("")}</ul>` : "");
  const sources = (state.ai.fuentes || []).slice(0, 12).map((s) => `<li><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">${esc(s.title)}</a></li>`).join("");
  root.innerHTML = `<h2 id="h-ia">Revisión mensual con IA</h2>
    <p class="muted">Del ${esc(when(state.ai.creada))}. Las tesis de cada empresa están en <a href="#ideas">Ideas</a>.</p>
    <div class="prose-block">
      ${r.resumen ? `<p>${inlineMd(r.resumen)}</p>` : ""}
      ${list("Para mirar este mes", r.alertas)}
      ${list("Próximos eventos", r.proximos_eventos)}
      ${sources ? `<h3>Fuentes que consultó</h3><ul class="sources">${sources}</ul>` : ""}
    </div>`;
}

// ---------- ideas ----------
function bar(label, v) {
  return `<div class="meter"><span>${label}</span><span class="meter-track"><span style="width:${v == null ? 0 : v}%"></span></span><b>${v == null ? "s/d" : nf(0).format(v)}</b></div>`;
}

function renderIdeas() {
  const root = $("#ideas");
  const ideas = state.ideas;
  const src = state.meta?.fuentes || {};
  const missing = [];
  if (state.meta && !src.sec) missing.push("fundamentos (falta el secreto SEC_CONTACTO)");
  if (state.meta && !src.patentes) missing.push("patentes (falta el secreto PATENTSVIEW_API_KEY)");
  $("#ideas-sources").textContent = missing.length ? `Sin datos de ${missing.join(" ni de ")}. El puntaje se calcula con lo disponible.` : "";
  if (!ideas) { root.innerHTML = '<p class="empty">Todavía no hay ideas. Aparecen después de la primera revisión diaria.</p>'; return; }
  const tb = tesisBy();
  const groups = new Map();
  for (const i of ideas) { if (!groups.has(i.grupo)) groups.set(i.grupo, []); groups.get(i.grupo).push(i); }
  root.innerHTML = [...groups.entries()].map(([g, items]) => {
    items.sort((a, b) => (b.puntaje ?? -1) - (a.puntaje ?? -1));
    return `<section class="idea-group"><h2>${esc(g)}</h2><ul class="rows">${items.map((i) => {
      if (i.sin_datos) return `<li class="row"><div class="row-main"><div><span class="sym">${esc(i.ticker)}</span><span class="sub">Sin datos en Yahoo Finance</span></div></div></li>`;
      const t = tb.get(i.ticker);
      const f = i.fundamentos || {};
      const s = i.sentimiento || {};
      const c = i.componentes || {};
      const tags = [];
      if (i.en_cartera) tags.push('<span class="tag gold">En tu cartera</span>');
      if (i.senal) tags.push(`<span class="badge ${esc(i.senal.accion)}">${esc(i.senal.accion)}</span>`);
      if ((s.fusiones || []).length) tags.push('<span class="tag">Posible fusión</span>');
      if (t) tags.push(`<span class="tag verdict-${esc(t.veredicto)}">IA: ${esc(VEREDICTOS[t.veredicto] || t.veredicto)}</span>`);
      const news = (i.noticias || []).slice(0, 6).map((n) => `<li><span class="tone ${n.tono > 0 ? "up" : n.tono < 0 ? "down" : "flat"}" aria-label="${n.tono > 0 ? "positiva" : n.tono < 0 ? "negativa" : "neutra"}">●</span> <a href="${esc(safeUrl(n.url))}" target="_blank" rel="noopener">${esc(n.titulo)}</a> <span class="muted">${esc(n.medio || "")}${n.fecha ? `, ${esc(n.fecha)}` : ""}</span></li>`).join("");
      const field = (label, v) => (v ? `<div><dt>${label}</dt><dd>${inlineMd(v)}</dd></div>` : "");
      return `<li class="row idea"><details><summary class="row-main clickable">
          <div><span class="sym">${esc(i.ticker)}</span> ${tags.join(" ")}<span class="sub">${esc(i.nombre || "")}</span></div>
          <div class="score" aria-label="Puntaje ${i.puntaje ?? "sin dato"} de 100"><b>${i.puntaje == null ? "—" : nf(0).format(i.puntaje)}</b><span class="muted">de 100</span></div>
          <div class="px"><b>${price(i.precio)} ${esc(i.moneda || "")}</b><span class="${trend(i.variacion_dia_pct)}">${pct(i.variacion_dia_pct, { signed: true, d: 2 })}</span></div>
        </summary>
        <div class="idea-body">
          <div class="meters">${bar("Tendencia 12 meses", c.momentum)}${bar("Fundamentos", c.fundamental)}${bar("Técnico", c.tecnico)}${bar("Noticias", c.sentimiento)}</div>
          <dl class="facts-grid">
            <div><dt>Últimos 12 meses</dt><dd>${pct(i.rend_1a_pct, { signed: true })}</dd></div>
            <div><dt>Anual promedio 5 años</dt><dd>${pct(i.rend_anual_5a_pct, { signed: true })}</dd></div>
            <div><dt>Peor caída 5 años</dt><dd>${pct(i.caida_maxima_pct)}</dd></div>
            <div><dt>Crecimiento de ingresos</dt><dd>${pct(f.crecimiento_ingresos_pct, { signed: true })}${f.moneda && !String(f.moneda).startsWith("USD") ? ` <span class="muted">(en ${esc(f.moneda)})</span>` : ""}</dd></div>
            <div><dt>Margen neto</dt><dd>${pct(f.margen_neto_pct)}</dd></div>
            <div><dt>Precio / ganancia</dt><dd>${f.precio_ganancia == null ? "—" : nf(1).format(f.precio_ganancia)}</dd></div>
            ${i.patentes ? `<div><dt>Patentes en EE.UU., 12 meses</dt><dd>${nf(0).format(i.patentes.ultimos_12_meses)}${i.patentes.variacion_pct != null ? ` (${pct(i.patentes.variacion_pct, { signed: true, d: 0 })})` : ""}</dd></div>` : ""}
            <div><dt>Noticias del mes</dt><dd>${s.total ? `${s.positivas} positivas, ${s.negativas} negativas de ${s.total}` : "—"}</dd></div>
          </dl>
          ${t ? `<dl class="pos-fields thesis">${field("Tesis de la IA", t.tesis)}${field("Fundamentos", t.fundamentos)}${field("Sentimiento", t.sentimiento)}${field("Fusiones y adquisiciones", t.fusiones)}${field("Patentes y desarrollos", t.patentes)}${field("Qué rompería la tesis", t.riesgos)}</dl>` : ""}
          ${(s.fusiones || []).length ? `<h4>Menciones de fusiones o adquisiciones</h4><ul class="news">${s.fusiones.map((n) => `<li><a href="${esc(safeUrl(n.url))}" target="_blank" rel="noopener">${esc(n.titulo)}</a></li>`).join("")}</ul>` : ""}
          ${news ? `<h4>Titulares recientes</h4><ul class="news">${news}</ul>` : ""}
          <p class="tools"><a href="${yahoo(i.ticker)}" target="_blank" rel="noopener">Ver en Yahoo Finanzas</a></p>
        </div>
      </details></li>`;
    }).join("")}</ul></section>`;
  }).join("");
}

// ---------- señales y mercados ----------
function renderSignals() {
  const ul = $("#signals");
  const rows = state.signals;
  if (!rows) { ul.innerHTML = '<li class="empty">Todavía no hay señales. Aparecen después de la primera revisión diaria.</li>'; return; }
  const f = state.filter;
  const list = rows.filter((r) => f === "todas" || (f === "cartera" ? r.en_cartera : r.accion === f));
  if (!list.length) { ul.innerHTML = '<li class="empty">No hay instrumentos con este filtro hoy.</li>'; return; }
  ul.innerHTML = list.map((r) => {
    const star = r.en_cartera ? ' <span class="star" title="Está en tu cartera">★</span>' : "";
    if (r.sin_datos) return `<li class="row"><div class="row-main"><div><span class="sym">${esc(r.symbol)}</span>${star}<span class="sub">Yahoo Finance no tiene datos de este instrumento</span></div><span></span><div class="px flat">—</div></div></li>`;
    const sp = r.spark || [];
    return `<li class="row"><details><summary class="row-main clickable">
        <div><span class="badge ${esc(r.accion)}">${esc(r.accion)}</span><span class="sym">${esc(r.symbol)}</span>${star}
          <span class="sub">${esc(r.nombre || "")}</span><span class="reasons-line">${esc((r.motivos || [])[0] || "")}</span></div>
        ${spark(sp, trend(sp.length > 1 ? sp[sp.length - 1] - sp[0] : 0))}
        <div class="px"><b>${price(r.precio)} ${esc(r.moneda || "")}</b><span class="${trend(r.variacion_dia_pct)}">${pct(r.variacion_dia_pct, { signed: true, d: 2 })}</span></div>
      </summary>
      <ul class="reasons">${(r.motivos || []).map((m) => `<li>${esc(m)}</li>`).join("")}<li>Puntaje ${esc(r.puntaje)}. <a href="${yahoo(r.symbol)}" target="_blank" rel="noopener">Ver en Yahoo Finanzas</a></li></ul>
    </details></li>`;
  }).join("");
}

function renderMarkets() {
  const ul = $("#markets");
  if (!state.markets) { ul.innerHTML = '<li class="empty">Todavía no hay datos. Aparecen después de la primera revisión diaria.</li>'; return; }
  ul.innerHTML = state.markets.map((m) => {
    const sp = m.spark || [];
    const month = sp.length > 1 ? ((sp[sp.length - 1] / sp[0]) - 1) * 100 : null;
    return `<li class="row"><a class="row-main" style="text-decoration:none;color:inherit" href="${yahoo(m.symbol)}" target="_blank" rel="noopener">
      <div><span class="sym">${esc(m.name)}</span><span class="sub">${esc(m.region)}${month != null ? `, ${pct(month, { signed: true })} en el mes` : ""}</span></div>
      ${spark(sp, trend(month))}
      <div class="px"><b>${price(m.price)}</b><span class="${trend(m.change_pct)}">${pct(m.change_pct, { signed: true, d: 2 })}</span></div>
    </a></li>`;
  }).join("");
}

function renderLinks() {
  $("#links").innerHTML = LINKS.map(([title, items]) => `<section><h2>${esc(title)}</h2><ul>${items.map(([n, d, u]) =>
    `<li><a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a><span>${esc(d)}</span></li>`).join("")}</ul></section>`).join("");
}

// ---------- IA desde el navegador (opcional) ----------
async function askClaude(system, user) {
  const key = lsGet(LS.key);
  if (!key) throw new Error("Falta tu clave de la API de Anthropic. Cargala en Ayuda.");
  const messages = [{ role: "user", content: user }];
  const parts = [];
  for (let i = 0; i < 5; i++) {
    let res;
    try {
      res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json", "anthropic-dangerous-direct-browser-access": "true" },
        body: JSON.stringify({ model: state.prompt?.modelo || DEFAULT_MODEL, max_tokens: 4000, system, messages, tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 4 }] }),
      });
    } catch { throw new Error("No hubo conexión con la IA. Revisá tu internet y probá de nuevo."); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401) throw new Error("La clave de la API no es válida. Revisala en Ayuda.");
      if (res.status === 429) throw new Error("Se alcanzó el límite de uso de la API. Probá de nuevo en un rato.");
      throw new Error(`Error ${res.status} de la IA. ${data?.error?.message || ""}`.trim());
    }
    for (const b of data.content || []) if (b.type === "text") parts.push(b.text || "");
    if (data.stop_reason === "pause_turn") { messages.push({ role: "assistant", content: data.content }); continue; }
    break;
  }
  return parts.join("").trim();
}

async function ask(e) {
  e.preventDefault();
  if (state.busy) return;
  const q = $("#ask-form").pregunta.value.trim();
  const out = $("#ask-answer");
  if (!q) return;
  if (!lsGet(LS.key)) { setStatus(out, 'Para preguntarle a la IA, cargá tu clave en <a href="#ayuda">Ayuda</a>.', "error"); return; }
  state.busy = true; $("#ask-btn").disabled = true;
  setStatus(out, working("La IA está pensando tu pregunta…"));
  try {
    const hoy = new Date().toLocaleDateString("es-AR", { day: "numeric", month: "long", year: "numeric" });
    const system = (state.prompt?.seguimiento || "Sos un analista de inversiones de largo plazo. Respondé en español rioplatense. Hoy es {hoy}.").replaceAll("{hoy}", hoy);
    const p = state.plan || {};
    const context = {
      perfil: p.perfil, distribucion: (p.grupos || []).map((g) => ({ nombre: g.nombre, objetivo: g.peso, actual: g.actual_pct, candidatos: g.candidatos })),
      cartera: p.cartera, sugerencia_del_mes: p.sugerencia, ranking: p.ranking, revision_ia: state.ai?.revision?.resumen,
    };
    const text = await askClaude(system, `Mi plan y mi cartera:\n${JSON.stringify(context)}\n\nMi pregunta:\n${q}`);
    out.className = "answer"; out.innerHTML = inlineMd(text);
    $("#ask-form").pregunta.value = "";
  } catch (err) { setStatus(out, esc(err.message), "error"); }
  finally { state.busy = false; $("#ask-btn").disabled = false; }
}

// ---------- ajustes ----------
function renderKeys() {
  const k = lsGet(LS.key), g = lsGet(LS.github);
  $("#key-status").textContent = `${g ? "Token de GitHub guardado." : "Sin token de GitHub."} ${k ? `Clave de la IA guardada (termina en …${k.slice(-4)}).` : "Sin clave de la IA."}`;
  const m = state.meta;
  if (!m) { $("#sources-status").textContent = "Todavía no corrió la primera revisión diaria."; $("#channels-status").textContent = ""; return; }
  const yes = (b) => (b ? "activo" : "sin configurar");
  $("#sources-status").textContent = `Fundamentos de la SEC: ${yes(m.fuentes?.sec)}. Patentes: ${yes(m.fuentes?.patentes)}. Revisión mensual con IA: ${yes(m.fuentes?.ia)}. Precios, señales y noticias: activos y gratis.`;
  const on = Object.entries(m.avisos || {}).filter(([, v]) => v).map(([n]) => (n === "ntfy" ? "ntfy" : "Telegram"));
  $("#channels-status").textContent = on.length ? `Avisos activos por: ${on.join(" y ")}.` : "Todavía no configuraste los avisos al celular.";
}

// ---------- inicio ----------
async function init() {
  route();
  window.addEventListener("hashchange", route);
  renderLinks();
  const now = new Date();
  $("#month-name").textContent = MESES[now.getMonth()];
  const f = $("#register-form");
  f.fecha.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  f.ticker.addEventListener("change", fillPrice);
  f.addEventListener("submit", register);
  $("#amount").addEventListener("input", () => { lsSet(LS.amount, $("#amount").value); renderSuggestion(); });
  $("#ask-form").addEventListener("submit", ask);
  document.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => {
    state.filter = b.dataset.filter;
    document.querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === b));
    renderSignals();
  }));
  $("#key-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const k = e.target;
    if (k.clave.value.trim()) lsSet(LS.key, k.clave.value.trim());
    if (k.github.value.trim()) lsSet(LS.github, k.github.value.trim());
    k.clave.value = ""; k.github.value = "";
    renderKeys();
  });
  $("#clear-keys").addEventListener("click", () => { lsSet(LS.key, ""); lsSet(LS.github, ""); renderKeys(); });

  const [meta, plan, ideas, ai, signals, markets, prompt] = await Promise.all(
    ["meta.json", "plan.json", "ideas.json", "ai.json", "signals.json", "markets.json", "prompt.json"].map(loadJson),
  );
  Object.assign(state, { meta, plan, ideas, ai, signals, markets, prompt });

  const saved = lsGet(LS.amount);
  $("#amount").value = saved || (plan?.perfil?.aporte_mensual_usd ? Math.round(plan.perfil.aporte_mensual_usd) : 100);
  $("#tickers").innerHTML = Object.keys(plan?.precios || {}).sort().map((t) => `<option value="${esc(t)}">`).join("");
  $("#stamp").textContent = meta?.actualizado ? `Actualizado ${when(meta.actualizado)}` : "Sin datos todavía: falta la primera revisión diaria";

  renderSuggestion();
  renderAiOnContribution();
  renderSleeves();
  renderHoldings();
  renderAiReview();
  renderIdeas();
  renderSignals();
  renderMarkets();
  renderKeys();
}

init();
