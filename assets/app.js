(() => {
// Datos: Contents API (fresca, sin la caché de ~10 min de Pages); si falla, data/data.json de Pages.
// Escritura (config.json, dispatch de buscar.yml): token fine-grained guardado solo en este navegador.
const REPO = "SMVictorOrtiz/flight_search_page";
const API = `https://api.github.com/repos/${REPO}`;
const WORKFLOW = "buscar.yml";
const TOKEN_KEY = "vuelos-token";
const STALE_H = 3;

const $ = (id) => document.getElementById(id);
const DIAS = ["dom","lun","mar","mié","jue","vie","sáb"];
const MESES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
const mxn = (n) => n == null ? "—" : "$" + Math.round(n).toLocaleString("en-US");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeLink = (u) => /^https:\/\/(www\.)?google\.[a-z.]+\//.test(u || "") ? esc(u) : "";
const dt = (iso) => new Date(iso + "T12:00:00");
const fdate = (iso) => { const d = dt(iso); return `${DIAS[d.getDay()]} ${d.getDate()} ${MESES[d.getMonth()]}`; };
const fday = (iso) => { const d = dt(iso); return `${d.getDate()} ${MESES[d.getMonth()]}`; };
// El motor escribe hora de México sin zona ("2026-10-22T23:07"); México ya no cambia de horario: UTC−6.
const ts = (s) => s ? new Date(s.length <= 16 ? s + ":00-06:00" : s) : null;
const fstamp = (s) => { const d = ts(s); if (!d) return ""; return `${d.getDate()} ${MESES[d.getMonth()]}, ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`; };
const ago = (d) => { const h = (Date.now() - d) / 36e5; return h < 1 ? `${Math.max(1, Math.round(h * 60))} min` : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} días`; };
const addDays = (iso, n) => { const d = dt(iso); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
const nights = (a, b) => Math.round((dt(b) - dt(a)) / 864e5);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clone = (o) => JSON.parse(JSON.stringify(o));

let DATA = null, latest = {}, hist = {}, days = [];
let base = null, cfg = null, configSha = null, searched = null;
let view = "group", sel = null, histMode = "best", optMode = "combos", showAll = false;

// ---------- GitHub ----------
let token = null;
try { token = localStorage.getItem(TOKEN_KEY); } catch (e) {}

async function gh(path, { method = "GET", body, raw = false, auth = true } = {}) {
  const headers = { Accept: raw ? "application/vnd.github.raw+json" : "application/vnd.github+json" };
  if (token && auth) headers.Authorization = `Bearer ${token}`;
  let r;
  try { r = await fetch(API + path, { method, headers, cache: "no-store", body: body ? JSON.stringify(body) : undefined }); }
  catch (e) { const err = new Error("red"); err.status = 0; throw err; }
  if (!r.ok) { const err = new Error(`GitHub ${r.status}`); err.status = r.status; try { err.body = await r.json(); } catch (e) {} throw err; }
  if (r.status === 204) return null;
  return raw ? r.text() : r.json();
}
const b64encode = (str) => { const bytes = new TextEncoder().encode(str); let bin = ""; bytes.forEach((b) => bin += String.fromCharCode(b)); return btoa(bin); };
const b64decode = (s) => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\s/g, "")), (c) => c.charCodeAt(0)));

async function fetchData() {
  try { return JSON.parse(await gh("/contents/data/data.json?ref=main", { raw: true })); }
  catch (e) {
    if (e.status === 401) { tokenRejected(); try { return JSON.parse(await gh("/contents/data/data.json?ref=main", { raw: true, auth: false })); } catch (e2) {} }
  }
  const r = await fetch("data/data.json?t=" + Date.now(), { cache: "no-store" });
  if (!r.ok) throw new Error("pages " + r.status);
  return r.json();
}
const okCfg = (c) => c && typeof c === "object" && c.ida_centro && c.vuelta_centro && c.adultos ? c : null;
async function fetchConfig() {
  if (token) {
    try { const f = await gh("/contents/config.json?ref=main"); const c = okCfg(JSON.parse(b64decode(f.content))); if (c) { configSha = f.sha; return c; } }
    catch (e) { if (e.status === 401) tokenRejected(); }
  }
  try { const c = okCfg(JSON.parse(await gh("/contents/config.json?ref=main", { raw: true, auth: false }))); if (c) return c; } catch (e) {}
  try { const r = await fetch("config.json?t=" + Date.now(), { cache: "no-store" }); if (r.ok) { const c = okCfg(await r.json()); if (c) return c; } } catch (e) {}
  return null;
}

// ---------- modelo ----------
const xOn = () => !!(cfg.grupo_cdmx && cfg.grupo_cdmx.adultos);
const xN = () => xOn() ? cfg.grupo_cdmx.adultos : 0;
const people = () => cfg.adultos + xN();
const bus = (ap) => ap === cfg.origen ? 0 : ((cfg.aeropuertos_alternos || {})[ap] || 0);
const range = (c, flex) => { const o = []; for (let i = -flex; i <= flex; i++) o.push(addDays(c, i)); return o; };
const idas = () => range(cfg.ida_centro, cfg.flex_dias);
const vtas = () => range(cfg.vuelta_centro, cfg.flex_dias);
const groupAps = () => [cfg.origen, ...Object.keys(cfg.aeropuertos_alternos || {})];

function bestLeg(dir, f, src) {      // src: latest o {ap: price} de un día
  let best = null;
  for (const ap of groupAps()) {
    const v = src(`${dir}|${ap}|${f}`); if (!v) continue;
    const cost = v.precio_total + bus(ap) * cfg.adultos;
    if (!best || cost < best.cost) best = { ap, v, cost, bus: bus(ap) * cfg.adultos };
  }
  return best;
}
function bestX(dir, f, src) {
  let best = null;
  for (const ap of (cfg.grupo_cdmx.aeropuertos || [])) {
    const v = src(`${dir}_cdmx|${ap}|${f}`); if (!v) continue;
    if (!best || v.precio_total < best.cost) best = { ap, v, cost: v.precio_total };
  }
  return best;
}
const fromLatest = (k) => latest[k];
function combo(fi, fv, src = fromLatest, withX = xOn()) {
  const n = nights(fi, fv);
  if ((cfg.excluir_ida || []).includes(fi) || (cfg.excluir_vuelta || []).includes(fv)) return { void: "excluida", n };
  if (n < cfg.noches_min || n > cfg.noches_max) return { void: "noches", n };
  const a = bestLeg("ida", fi, src), b = bestLeg("vuelta", fv, src);
  if (!a || !b) return { void: "sin vuelo", n };
  let xi = null, xv = null;
  if (withX) { xi = bestX("ida", fi, src); xv = bestX("vuelta", fv, src); if (!xi || !xv) return { void: "sin precio 4º", n }; }
  const bags = (cfg.costo_equipaje_por_persona_tramo || 0) * (cfg.adultos + (withX ? xN() : 0)) * 2;
  const grupo = a.v.precio_total + b.v.precio_total, busT = a.bus + b.bus, x = withX ? xi.cost + xv.cost : 0;
  return { fi, fv, n, a, b, xi, xv, grupo, bus: busT, x, bags, total: grupo + busT + x + bags };
}
function allCombos() {
  const out = [];
  for (const fi of idas()) for (const fv of vtas()) { const c = combo(fi, fv); if (!c.void) out.push(c); }
  return out.sort((p, q) => p.total - q.total);
}
const goal = () => cfg.umbral_total_mxn;
const bestTotal = () => allCombos()[0]?.total ?? null;

// ---------- respuesta ----------
function renderAnswer() {
  document.querySelector(".target").hidden = false;
  const list = allCombos(); const best = list[0];
  const c = sel ? combo(sel[0], sel[1]) : best;
  $("backBest").hidden = !sel || (best && sel[0] === best.fi && sel[1] === best.fv);
  const who = xOn() ? `${people()} (${cfg.adultos} de Puebla + ${xN()} de CDMX)` : `${cfg.adultos} desde Puebla`;
  if (!c || c.void) {
    $("ansTitle").textContent = "Sin combinación válida";
    $("ansTotal").textContent = "—"; $("ansFacts").textContent = "Ninguna fecha cumple las reglas con los precios buscados.";
    $("legs").innerHTML = ""; $("stack").innerHTML = ""; $("verdict").textContent = ""; $("tfill").style.width = "0"; $("tmax").textContent = ""; return;
  }
  const isBest = best && c.fi === best.fi && c.fv === best.fv;
  $("ansTitle").textContent = (isBest ? "Mejor combinación para " : "Combinación elegida para ") + who;
  $("ansTotal").innerHTML = `${mxn(c.total)}<small>${mxn(c.total / people())} por persona</small>`;
  $("ansFacts").innerHTML = `<span>${fdate(c.fi)} → ${fdate(c.fv)}</span><span>${c.n} noches</span><span>Solo vuelos directos</span>`;
  const g = goal(), diff = c.total - g;
  $("verdict").className = "verdict " + (diff > 0 ? "over" : "ok");
  $("verdict").innerHTML = diff > 0
    ? `<b class="num">${mxn(diff)} arriba</b> de tu meta de ${mxn(g)}`
    : `<b class="num">${mxn(-diff)} abajo</b> de tu meta de ${mxn(g)}. Buen momento para comprar.`;
  const max = Math.max(g, c.total) * 1.1;
  $("tfill").style.width = (c.total / max * 100) + "%";
  $("tfill").style.background = diff > 0 ? "var(--bad)" : "var(--good)";
  $("tmax").textContent = "meta " + mxn(g);
  const segs = [["Vuelos desde Puebla", c.grupo, "--seg1"], ["Camión", c.bus, "--seg2"], ["Vuelos desde CDMX", c.x, "--seg3"], ["Maletas", c.bags, "--seg2"]].filter(s => s[1] > 0);
  $("stack").innerHTML = segs.map(s => `<span style="flex-grow:${s[1]};background:var(${s[2]})" title="${s[0]} ${mxn(s[1])}"></span>`).join("");
  const leg = (sw, title, detail, price, link) => `<div class="leg"><i class="sw" style="background:var(${sw})"></i><div><div class="t">${title}</div><div class="d">${detail}</div></div><div class="p num">${mxn(price)}${safeLink(link) ? `<a href="${safeLink(link)}" target="_blank" rel="noopener">Google Flights</a>` : ""}</div></div>`;
  const fl = (x) => esc(`${x.v.aerolinea} ${x.v.vuelo} · ${x.v.de || x.ap} ${x.v.salida} → ${x.v.a} ${x.v.llegada}`);
  let h = "";
  h += leg("--seg1", `Ida ${cfg.adultos} desde ${c.a.ap}`, fl(c.a) + ` · visto ${fstamp(c.a.v.cuando)}`, c.a.v.precio_total, c.a.v.link);
  h += leg("--seg1", `Vuelta ${cfg.adultos} a ${c.b.ap}`, fl(c.b) + ` · visto ${fstamp(c.b.v.cuando)}`, c.b.v.precio_total, c.b.v.link);
  if (c.bus) h += leg("--seg2", "Camión Puebla ⇄ aeropuerto", `${[c.a.ap, c.b.ap].filter(a => a !== cfg.origen).join(" y ")} · ${cfg.adultos} personas`, c.bus);
  if (c.xi) {
    const tog = (x, g2) => x.v.vuelo && x.v.vuelo === g2.v.vuelo ? `<span class="together">mismo vuelo</span>` : "";
    h += leg("--seg3", `Ida ${xN()} desde ${c.xi.ap}${tog(c.xi, c.a)}`, fl(c.xi), c.xi.cost, c.xi.v.link);
    h += leg("--seg3", `Vuelta ${xN()} a ${c.xv.ap}${tog(c.xv, c.b)}`, fl(c.xv), c.xv.cost, c.xv.v.link);
  }
  if (c.bags) h += leg("--seg2", "Maletas", `${mxn(cfg.costo_equipaje_por_persona_tramo)} por persona y tramo`, c.bags);
  h += `<div class="leg total"><i></i><div class="t">Total</div><div class="p num">${mxn(c.total)}</div></div>`;
  $("legs").innerHTML = h;
}

// ---------- matriz ----------
const BANDS = [["--verde", "Más barato"], ["--amarillo", ""], ["--rosa", ""], ["--rojo", "Más caro"]];
function renderMatrix() {
  const exI = cfg.excluir_ida || [], exV = cfg.excluir_vuelta || [];
  const I = idas().filter(f => !exI.includes(f)), V = vtas().filter(f => !exV.includes(f)), list = allCombos();
  const hiddenTxt = [...idas().filter(f => exI.includes(f)).map(f => "ida " + fday(f)), ...vtas().filter(f => exV.includes(f)).map(f => "vuelta " + fday(f))];
  const prices = list.map(c => c.total).sort((a, b) => a - b);
  const q = (p) => prices.length ? prices[Math.min(prices.length - 1, Math.floor(p * prices.length))] : 0;
  const cuts = [q(.25), q(.5), q(.75)];
  const band = (t) => t <= cuts[0] ? 0 : t <= cuts[1] ? 1 : t <= cuts[2] ? 2 : 3;
  const best = list[0];
  const mx = $("mx"); mx.style.setProperty("--cols", V.length);
  let h = `<div class="h"><span>ida ↓</span><span>vuelta →</span></div>`;
  for (const fv of V) h += `<div class="h col"><b>${fday(fv)}</b>${DIAS[dt(fv).getDay()]}</div>`;
  for (const fi of I) {
    h += `<div class="h rowh"><b>${fday(fi)}</b>${DIAS[dt(fi).getDay()]}</div>`;
    for (const fv of V) {
      const c = combo(fi, fv);
      if (c.void) { h += `<div class="cell void" role="gridcell"><span class="chip">${c.void === "noches" ? c.n + " noches" : c.void}</span></div>`; continue; }
      const b = band(c.total), isSel = sel ? sel[0] === fi && sel[1] === fv : best && best.fi === fi && best.fv === fv;
      const isBest = best && best.fi === fi && best.fv === fv;
      h += `<button type="button" class="cell${isBest ? " best" : ""}" role="gridcell" aria-pressed="${isSel}" data-i="${fi}" data-v="${fv}" style="--band:var(${BANDS[b][0]})" aria-label="Ida ${fdate(fi)}, vuelta ${fdate(fv)}: ${mxn(c.total)}"><span class="chip num">${mxn(c.total)}<small>${isBest ? "mejor" : c.total <= goal() ? "en meta" : c.n + " n"}</small></span></button>`;
    }
  }
  mx.innerHTML = h;
  if (!prices.length) { $("legend").innerHTML = `<span>Todavía no hay precios para estas fechas. ${view === "editor" ? "Guarda y busca para llenarlas." : ""}</span>`; return; }
  const rng = [[prices[0], cuts[0]], [cuts[0], cuts[1]], [cuts[1], cuts[2]], [cuts[2], prices[prices.length - 1]]];
  $("legend").innerHTML = BANDS.map((b, i) => `<span><i style="--band:var(${b[0]})"></i><span class="num">${mxn(rng[i][0])}–${mxn(rng[i][1])}</span></span>`).join("") +
    `<span>Punteado: fuera del rango de noches</span>` + (hiddenTxt.length ? `<span>Sin ${hiddenTxt.join(" ni ")}, por tus reglas</span>` : "");
}
$("mx").addEventListener("click", (e) => {
  const b = e.target.closest("button.cell"); if (!b) return;
  sel = [b.dataset.i, b.dataset.v]; renderAll();
});
$("backBest").onclick = () => { sel = null; renderAll(); };

// ---------- historial ----------
function seriesFor(fi, fv) {     // total del grupo de Puebla por día (mínimo del día)
  return days.map(d => { const src = (k) => hist[k] && hist[k][d] != null ? { precio_total: hist[k][d] } : null; const c = combo(fi, fv, src, false); return c.void ? null : c.total; });
}
function seriesBest() {
  return days.map(d => { let m = null; const src = (k) => hist[k] && hist[k][d] != null ? { precio_total: hist[k][d] } : null;
    for (const fi of idas()) for (const fv of vtas()) { const c = combo(fi, fv, src, false); if (!c.void && (m == null || c.total < m)) m = c.total; } return m; });
}
function niceStep(span) { const raw = Math.max(span, 1) / 4, p = Math.pow(10, Math.floor(Math.log10(raw))); for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= raw) return m * p; return 10 * p; }
function cdmxSince() {
  let first = null;
  for (const [k, h] of Object.entries(hist)) if (k.includes("_cdmx|")) for (const d of Object.keys(h)) if (!first || d < first) first = d;
  return first;
}
function renderHist() {
  const list = allCombos(), c = sel ? combo(sel[0], sel[1]) : list[0];
  const ys = histMode === "best" || !c || c.void ? seriesBest() : seriesFor(c.fi, c.fv);
  const ref = Math.round(goal() * cfg.adultos / people());
  const since = cdmxSince();
  $("histSub").textContent = (histMode === "best" ? "El total más bajo de cada día entre todas las fechas válidas" : `Ida ${fdate(c.fi)}, vuelta ${fdate(c.fv)}, mínimo de cada día`) +
    ` · ${cfg.adultos} desde Puebla con camión` + (xOn() ? (since ? `. El 4º se busca desde el ${fday(since)}; aquí se grafica solo el grupo de Puebla.` : ". El 4º aún no tiene historial.") : ".");
  const chart = $("chart"); chart.querySelector(".ph")?.remove();
  const vals = ys.filter(v => v != null);
  if (!vals.length || days.length < 2) {
    chart.querySelector("svg")?.remove(); chart.querySelector(".fail-msg")?.remove();
    chart.insertAdjacentHTML("afterbegin", `<div class="fail-msg">Todavía no hay historial para estas fechas.</div>`);
    $("histfoot").innerHTML = ""; return;
  }
  chart.querySelector(".fail-msg")?.remove();
  const W = Math.max(320, chart.clientWidth || 800), H = W < 560 ? 190 : 230, L = 58, R = 12, T = 22, B = 26;
  let lo = Math.min(...vals, ref), hi = Math.max(...vals, ref); const st = niceStep(hi - lo);
  lo = Math.floor(lo / st) * st; hi = Math.ceil(hi / st) * st; if (hi === Math.max(...vals)) hi += st;
  const x = (i) => L + (W - L - R) * i / (days.length - 1), y = (v) => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Historial de precio">`;
  for (let v = lo; v <= hi + 1; v += st) s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)" stroke-width="1"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${mxn(v)}</text>`;
  days.forEach((d, i) => { if (dt(d).getDay() === 1) s += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${fday(d)}</text>`; });
  s += `<line x1="${L}" x2="${W - R}" y1="${y(ref)}" y2="${y(ref)}" stroke="var(--good)" stroke-width="1" stroke-dasharray="4 3"/><text x="${W - R}" y="${y(ref) - 6}" text-anchor="end" style="fill:var(--good)">meta para ${cfg.adultos}: ${mxn(ref)}</text>`;
  let path = "", pen = false; ys.forEach((v, i) => { if (v == null) { pen = false; return; } path += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1); pen = true; });
  s += `<path d="${path}" fill="none" stroke="var(--ink)" stroke-width="2" stroke-linejoin="round"/>`;
  const iMin = ys.indexOf(Math.min(...vals));
  let iLast = ys.length - 1; while (iLast > 0 && ys[iLast] == null) iLast--;
  s += `<line x1="${x(iMin)}" x2="${x(iMin)}" y1="${T - 6}" y2="${y(ys[iMin])}" stroke="var(--faint)" stroke-width="1"/><text x="${x(iMin)}" y="${T - 10}" text-anchor="${iMin < 3 ? "start" : iMin > days.length - 4 ? "end" : "middle"}" style="fill:var(--ink)">mínimo ${mxn(ys[iMin])} · ${fday(days[iMin])}</text>`;
  s += `<circle cx="${x(iLast)}" cy="${y(ys[iLast])}" r="4" fill="var(--ink)"/>`;
  s += `<rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent" id="hit"/></svg>`;
  chart.querySelector("svg")?.remove(); chart.insertAdjacentHTML("afterbegin", s);
  const tip = $("tip");
  $("hit").onpointermove = (e) => { const r = e.target.getBoundingClientRect(); const i = Math.max(0, Math.min(days.length - 1, Math.round((e.clientX - r.left) / r.width * (days.length - 1)))); if (ys[i] == null) return;
    tip.textContent = `${fday(days[i])}: ${mxn(ys[i])}`; tip.style.left = (x(i) / W * 100) + "%"; tip.style.top = (y(ys[i]) / H * 100) + "%"; tip.classList.add("show"); };
  $("hit").onpointerleave = () => tip.classList.remove("show");
  const wk = ys[Math.max(0, iLast - 7)], d7 = wk == null ? null : ys[iLast] - wk;
  $("histfoot").innerHTML = `<div class="kv"><span>Hoy</span><b class="num">${mxn(ys[iLast])}</b></div>
    <div class="kv"><span>Hace 7 días</span><b class="num">${mxn(wk)}</b></div>
    <div class="kv"><span>Cambio en 7 días</span><b class="num delta ${d7 > 0 ? "up" : d7 < 0 ? "down" : "flat"}">${d7 == null ? "—" : (d7 > 0 ? "+" : d7 < 0 ? "−" : "") + mxn(Math.abs(d7))}</b></div>
    <div class="kv"><span>Mínimo visto</span><b class="num">${mxn(ys[iMin])}</b></div>`;
}
$("hBest").onclick = () => { histMode = "best"; $("hBest").setAttribute("aria-pressed", true); $("hSel").setAttribute("aria-pressed", false); renderHist(); };
$("hSel").onclick = () => { histMode = "sel"; $("hSel").setAttribute("aria-pressed", true); $("hBest").setAttribute("aria-pressed", false); renderHist(); };

// ---------- opciones ----------
function weekAgo(k) { const h = hist[k]; if (!h) return null; const ds = Object.keys(h).sort(); const tgt = addDays(ds[ds.length - 1], -7); return h[tgt] ?? null; }
function renderOpts() {
  const t = $("table");
  $("legFilters").hidden = optMode !== "legs";
  $("fGroup").options[1].textContent = `Desde Puebla (${searched.adultos})`;
  $("fGroup").options[2].textContent = `Desde CDMX (${searched.xn || 1})`;
  if (optMode === "combos") {
    const list = allCombos(), shown = showAll ? list : list.slice(0, 8), best = list[0];
    let h = `<thead><tr><th>Fechas</th><th>Ida</th><th>Vuelta</th>${xOn() ? "<th>Desde CDMX</th>" : ""}<th class="r">Camión</th><th class="r">Total</th><th class="r">Por persona</th></tr></thead><tbody>`;
    for (const c of shown) {
      const isSel = sel ? sel[0] === c.fi && sel[1] === c.fv : c === best;
      h += `<tr class="${isSel ? "pick" : ""}"><td>${fday(c.fi)} → ${fday(c.fv)}<span class="d">${c.n} noches${c.total <= goal() ? ' · <span class="pill g">en meta</span>' : ""}</span></td>
        <td class="hide-sm">${c.a.ap} · ${esc(c.a.v.vuelo)}<span class="d num">${esc(c.a.v.salida)} · ${mxn(c.a.v.precio_total)}</span></td>
        <td class="hide-sm">${c.b.ap} · ${esc(c.b.v.vuelo)}<span class="d num">${esc(c.b.v.salida)} · ${mxn(c.b.v.precio_total)}</span></td>
        ${xOn() ? `<td class="hide-sm">${c.xi.ap} → ${c.xv.ap}<span class="d num">${mxn(c.x)}</span></td>` : ""}
        <td class="r num hide-sm">${c.bus ? mxn(c.bus) : "—"}</td><td class="r num"><b>${mxn(c.total)}</b></td><td class="r num hide-sm">${mxn(c.total / people())}</td></tr>`;
    }
    if (!list.length) h += `<tr><td colspan="7">Ninguna combinación cumple las reglas con los precios buscados.</td></tr>`;
    t.innerHTML = h + "</tbody>";
    $("moreBtn").hidden = list.length <= 8;
    $("moreBtn").textContent = showAll ? "Ver menos" : `Ver las ${list.length} combinaciones`;
  } else {
    const fd = $("fDir").value, fg = $("fGroup").value, fa = $("fAp").value;
    let rows = Object.entries(latest).map(([k, v]) => { const [dir, ap, f] = k.split("|"); return { k, dir: dir.replace("_cdmx", ""), cdmx: dir.endsWith("_cdmx"), ap, f, v, wk: weekAgo(k) }; })
      .filter(r => (!fd || r.dir === fd) && (!fg || (fg === "c") === r.cdmx) && (!fa || r.ap === fa));
    rows.sort((a, b) => a.dir.localeCompare(b.dir) || a.f.localeCompare(b.f) || a.v.precio_total - b.v.precio_total);
    let h = `<thead><tr><th>Vuelo</th><th>Fecha</th><th>Ruta</th><th class="r">Precio</th><th class="r">Por persona</th><th class="r">vs hace 7 días</th><th>Visto</th></tr></thead><tbody>`;
    for (const r of rows) {
      const n = r.cdmx ? searched.xn : searched.adultos, d = r.wk == null ? null : r.v.precio_total - r.wk;
      const link = safeLink(r.v.link);
      h += `<tr><td>${esc(r.v.aerolinea)} ${esc(r.v.vuelo)}<span class="d">${r.dir === "ida" ? "Ida" : "Vuelta"} · ${r.cdmx ? "desde CDMX" : "grupo Puebla"} (${n})</span></td>
        <td class="r-sm">${fdate(r.f)}<span class="d num">${esc(r.v.salida)} → ${esc(r.v.llegada)}</span></td>
        <td class="hide-sm">${esc(r.v.de)} → ${esc(r.v.a)}</td>
        <td class="r num">${link ? `<a href="${link}" target="_blank" rel="noopener">${mxn(r.v.precio_total)}</a>` : mxn(r.v.precio_total)}</td>
        <td class="r num hide-sm">${mxn(r.v.precio_total / n)}</td>
        <td class="r num hide-sm">${d == null ? '<span class="delta flat">—</span>' : `<span class="delta ${d > 0 ? "up" : d < 0 ? "down" : "flat"}">${d > 0 ? "+" : d < 0 ? "−" : ""}${mxn(Math.abs(d))}</span>`}</td>
        <td class="meta hide-sm">${fstamp(r.v.cuando)}</td></tr>`;
    }
    t.innerHTML = h + (rows.length ? "" : `<tr><td colspan="7">Ningún vuelo coincide con estos filtros.</td></tr>`) + "</tbody>";
    $("moreBtn").hidden = true;
  }
}
$("oCombos").onclick = () => { optMode = "combos"; $("oCombos").setAttribute("aria-pressed", true); $("oLegs").setAttribute("aria-pressed", false); renderOpts(); };
$("oLegs").onclick = () => { optMode = "legs"; $("oLegs").setAttribute("aria-pressed", true); $("oCombos").setAttribute("aria-pressed", false); renderOpts(); };
["fDir", "fGroup", "fAp"].forEach(id => $(id).onchange = renderOpts);
$("moreBtn").onclick = () => { showAll = !showAll; renderOpts(); };

// ---------- reglas ----------
const F = { cAdults: ["adultos", "n"], cIda: ["ida_centro"], cVta: ["vuelta_centro"], cFlex: ["flex_dias", "n"], cNmin: ["noches_min", "n"], cNmax: ["noches_max", "n"], cGoal: ["umbral_total_mxn", "n"], cBags: ["costo_equipaje_por_persona_tramo", "n"] };
function fillForm() {
  for (const [id, [k]] of Object.entries(F)) $(id).value = cfg[k] ?? "";
  const x = cfg.grupo_cdmx || {}; $("cXon").checked = !!x.adultos; $("cXn").value = x.adultos || searched.xn || 1;
  $("cXmex").checked = (x.aeropuertos || []).includes("MEX"); $("cXnlu").checked = (x.aeropuertos || []).includes("NLU");
  const alt = cfg.aeropuertos_alternos || {};
  $("cBusMex").value = alt.MEX ?? ""; $("cBusNlu").value = alt.NLU ?? "";
  $("cExIda").value = (cfg.excluir_ida || []).join(", "); $("cExVta").value = (cfg.excluir_vuelta || []).join(", ");
  $("goalHint").textContent = `${mxn(goal() / people())} por persona para ${people()}`;
  lockForm();
}
function lockForm() { document.querySelectorAll("#rules input").forEach(el => el.disabled = view !== "editor" || busy || (el.id === "cXn" && !$("cXon").checked)); }
function readForm() {
  for (const [id, [k, t]] of Object.entries(F)) { const v = $(id).value; if (v !== "") cfg[k] = t === "n" ? Number(v) : v; }
  const on = $("cXon").checked; $("cXn").disabled = !on;
  const aps = [$("cXmex").checked && "MEX", $("cXnlu").checked && "NLU"].filter(Boolean);
  cfg.grupo_cdmx = on ? { adultos: Number($("cXn").value) || 1, aeropuertos: aps, cada_horas: (base.grupo_cdmx || {}).cada_horas || 1 } : {};
  cfg.aeropuertos_alternos = { ...(cfg.aeropuertos_alternos || {}), MEX: Number($("cBusMex").value) || 0, NLU: Number($("cBusNlu").value) || 0 };
  const list = (s) => s.split(",").map(t => t.trim()).filter(t => /^\d{4}-\d{2}-\d{2}$/.test(t));
  cfg.excluir_ida = list($("cExIda").value); cfg.excluir_vuelta = list($("cExVta").value);
  $("goalHint").textContent = `${mxn(goal() / people())} por persona para ${people()}`;
}
function needsSearch() {
  const why = [];
  if (cfg.adultos !== searched.adultos) why.push(`los precios guardados son para ${searched.adultos} desde Puebla`);
  if (xOn() && cfg.grupo_cdmx.adultos !== searched.xn) why.push(`los del 4º son para ${searched.xn} persona${searched.xn === 1 ? "" : "s"}`);
  if (xOn() && cfg.grupo_cdmx.aeropuertos.some(a => !searched.xaps.includes(a))) why.push("hay un aeropuerto de CDMX sin buscar");
  const known = new Set(Object.keys(latest).map(k => k.split("|")[2]));
  if ([...idas(), ...vtas()].some(f => !known.has(f) && !(cfg.excluir_ida || []).includes(f) && !(cfg.excluir_vuelta || []).includes(f))) why.push("hay fechas nuevas que nunca se han buscado");
  return why;
}
const dirty = () => JSON.stringify(cfg) !== JSON.stringify(base);
function renderSavebar() {
  const d = dirty();
  $("resetBtn").disabled = busy || !d;
  $("saveBtn").disabled = busy || !d;
  $("saveRunBtn").disabled = busy || running;
  $("saveRunBtn").textContent = d ? "Guardar y buscar" : "Buscar con estas reglas";
}
$("rules").addEventListener("input", (e) => {
  if (view !== "editor" || !e.target.matches("input, select")) return;
  readForm(); sel = null; renderAll();
});
$("resetBtn").onclick = () => { cfg = clone(base); fillForm(); sel = null; renderAll(); toast("Cambios descartados"); };

let busy = false;
function setBusy(b) { busy = b; lockForm(); renderSavebar(); }
async function save() {
  if (!dirty()) return true;
  setBusy(true); $("saveBtn").textContent = "Guardando…";
  try {
    const r = await gh("/contents/config.json", { method: "PUT", body: { message: "config: reglas del viaje desde la página", content: b64encode(JSON.stringify(cfg, null, 2) + "\n"), sha: configSha || undefined, branch: "main" } });
    configSha = r.content.sha; base = clone(cfg);
    toast("Guardado en config.json. La Mac y GitHub lo usan desde la próxima búsqueda.");
    return true;
  } catch (e) {
    if (e.status === 409 || (e.status === 422 && /sha/i.test(e.body?.message || ""))) {
      const fresh = await fetchConfig();
      if (fresh) { base = fresh; cfg = clone(fresh); fillForm(); renderAll(); }
      toast("config.json cambió en el repo mientras editabas. Cargué la versión actual: revisa y vuelve a guardar.", 6000);
    } else if (e.status === 401) { tokenRejected(); }
    else if (e.status === 403 || e.status === 404) toast("El token no puede escribir en el repo. Necesita Contents: lectura y escritura.", 6000);
    else if (e.status === 0) toast("No se pudo guardar: sin conexión con GitHub. Tus cambios siguen aquí.", 6000);
    else toast(`GitHub no aceptó el cambio (${e.status}). Tus cambios siguen aquí.`, 6000);
    return false;
  } finally { $("saveBtn").textContent = "Guardar"; setBusy(false); }
}
$("saveBtn").onclick = save;
$("saveRunBtn").onclick = async () => { if (await save()) run(); };

// ---------- buscar ahora: dispatch real + pasos del run ----------
const STEPS = ["En cola", "Buscando", "Publicando", "Listo"];
let running = false;
function showSteps(i, msg, failed = false) {
  $("runstrip").hidden = false;
  $("steps").innerHTML = STEPS.map((s, j) => `<span class="step ${j < i ? "done" : j === i ? (failed ? "fail" : "now") : ""}"><i></i>${s}</span>`).join("");
  $("runmsg").innerHTML = msg;
}
function setRunning(r) {
  running = r; $("runBtn").disabled = r; $("healthdot").classList.toggle("busy", r); renderSavebar();
}
function stepOf(run, jobs) {
  if (run.status !== "in_progress") return run.status === "completed" ? 3 : 0;
  const steps = (jobs?.jobs || []).flatMap(j => j.steps || []);
  const pub = steps.find(s => /publicar/i.test(s.name));
  if (pub && pub.status !== "queued") return 2;
  return steps.some(s => /buscar/i.test(s.name) && s.status !== "queued") ? 1 : 0;
}
const runLink = (r) => r?.html_url ? ` <a href="${esc(r.html_url)}" target="_blank" rel="noopener">Ver en GitHub</a>` : "";
async function run() {
  if (running || !token) return;
  setRunning(true);
  const before = bestTotal(), t0 = Date.now() - 15000;
  showSteps(0, "Pidiendo la búsqueda a GitHub…");
  try { await gh(`/actions/workflows/${WORKFLOW}/dispatches`, { method: "POST", body: { ref: "main" } }); }
  catch (e) {
    const why = e.status === 401 ? "GitHub rechazó el token." : e.status === 403 ? "El token no tiene permiso de Actions (lectura y escritura)." : e.status === 404 ? `No encontré ${WORKFLOW} en el repo, o el token no ve Actions.` : e.status === 0 ? "Sin conexión con GitHub." : `GitHub respondió ${e.status}.`;
    showSteps(0, `No se pudo arrancar la búsqueda. ${why}`, true); setRunning(false); if (e.status === 401) tokenRejected(); return;
  }
  let r = null;
  for (let i = 0; i < 30 && !r; i++) {
    await sleep(i ? 3000 : 1500);
    try { const list = await gh(`/actions/workflows/${WORKFLOW}/runs?event=workflow_dispatch&per_page=5`); r = list.workflow_runs.find(x => new Date(x.created_at) >= t0) || null; } catch (e) {}
  }
  if (!r) { showSteps(0, "GitHub aceptó la búsqueda pero no aparece el run. Revisa Actions en unos minutos.", true); setRunning(false); return; }
  track(r, before);
}
async function track(r, before) {
  setRunning(true);
  const deadline = Date.now() + 30 * 60e3; let i = 0, misses = 0;
  while (Date.now() < deadline) {
    try {
      r = await gh(`/actions/runs/${r.id}`);
      if (r.status === "completed") break;
      const jobs = await gh(`/actions/runs/${r.id}/jobs`);
      i = stepOf(r, jobs); misses = 0;
      showSteps(i, [`Esperando un runner de GitHub Actions…`, `Consultando Google Flights, unos 5 minutos.${runLink(r)}`, `Guardando data.json en el repo…${runLink(r)}`][i]);
    } catch (e) {
      if (++misses >= 5) { showSteps(i, `Perdí contacto con GitHub. La búsqueda puede seguir corriendo.${runLink(r)}`, true); setRunning(false); return; }
    }
    await sleep(5000);
  }
  if (r.status !== "completed") { showSteps(i, `La búsqueda lleva más de 30 minutos.${runLink(r)}`, true); setRunning(false); return; }
  if (r.conclusion !== "success") {
    const what = { failure: "falló", cancelled: "se canceló", timed_out: "se pasó del tiempo" }[r.conclusion] || `terminó como ${r.conclusion}`;
    showSteps(Math.max(i, 1), `La búsqueda ${what}. Los datos de la página no cambiaron.${runLink(r)}`, true); setRunning(false); return;
  }
  showSteps(2, "Cargando los precios nuevos…");
  const prev = DATA?.salud?.ultima_corrida;
  try { await load({ quiet: true }); } catch (e) {}
  const after = bestTotal();
  let msg;
  if (DATA?.salud?.ultima_corrida === prev) msg = "La búsqueda terminó pero no publicó precios nuevos (Google y SerpApi pudieron fallar)." + runLink(r);
  else if (before == null || after == null) msg = after == null ? "Listo. Todavía no hay una combinación válida." : `Listo. El total más bajo es <b>${mxn(after)}</b>.`;
  else if (after < before) msg = `Encontró un precio mejor: <b>${mxn(after)}</b>, bajó ${mxn(before - after)}.`;
  else if (after > before) msg = `Sin precio mejor. El total más bajo ahora es ${mxn(after)}, subió ${mxn(after - before)}.`;
  else msg = `Sin precio mejor. El total más bajo sigue en ${mxn(after)}.`;
  showSteps(4, msg); setRunning(false);
}
$("runBtn").onclick = run;
async function resumeRun() {
  try {
    const list = await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=1`);
    const r = list.workflow_runs[0];
    if (r && r.status !== "completed") track(r, bestTotal());
  } catch (e) {}
}

// ---------- token y vista ----------
function setView(v) {
  view = v; $("app").classList.toggle("editor", v === "editor"); $("app").classList.toggle("ro", v !== "editor");
  $("keyTxt").textContent = v === "editor" ? "Quitar token" : "Editar";
  if (v === "group" && base) { cfg = clone(base); sel = null; $("runstrip").hidden = true; }
  if (cfg) { fillForm(); renderAll(); }
}
function openTokenbar(msg) {
  $("tokenbar").hidden = false; $("keyBtn").setAttribute("aria-expanded", "true");
  $("tokenErr").hidden = !msg; $("tokenErr").textContent = msg || "";
  $("tokenIn").focus();
}
function closeTokenbar() { $("tokenbar").hidden = true; $("keyBtn").setAttribute("aria-expanded", "false"); $("tokenIn").value = ""; $("tokenErr").hidden = true; }
function forgetToken() { token = null; configSha = null; try { localStorage.removeItem(TOKEN_KEY); } catch (e) {} }
function tokenRejected() {
  if (!token) return;
  forgetToken(); setView("group");
  openTokenbar("GitHub rechazó el token guardado: está mal copiado o ya venció. Pega uno nuevo.");
}
async function checkToken(t) {
  const prev = token; token = t;
  try {
    const repo = await gh("");
    if (!repo.permissions?.push) { token = prev; return "El token solo puede leer el repo. Necesita Contents y Actions de lectura y escritura."; }
    return null;
  } catch (e) {
    token = prev;
    if (e.status === 401) return "GitHub rechazó el token: está mal copiado o ya venció.";
    if (e.status === 403 || e.status === 404) return `El token no tiene acceso a ${REPO}.`;
    if (e.status === 0) return "Sin conexión con GitHub. Intenta de nuevo.";
    return `GitHub respondió ${e.status}.`;
  }
}
$("keyBtn").onclick = () => {
  if (token) { forgetToken(); setView("group"); toast("Token quitado de este navegador"); return; }
  $("tokenbar").hidden ? openTokenbar() : closeTokenbar();
};
$("tokenCancel").onclick = closeTokenbar;
$("tokenbar").onsubmit = async (e) => {
  e.preventDefault();
  const t = $("tokenIn").value.trim(); if (!t) { $("tokenIn").focus(); return; }
  $("tokenSave").disabled = true; $("tokenSave").textContent = "Revisando…";
  const err = await checkToken(t);
  $("tokenSave").disabled = false; $("tokenSave").textContent = "Usar token";
  if (err) { $("tokenErr").hidden = false; $("tokenErr").textContent = err; return; }
  token = t; try { localStorage.setItem(TOKEN_KEY, t); } catch (e2) {}
  closeTokenbar();
  const fresh = await fetchConfig(); if (fresh) base = fresh;
  setView("editor"); toast("Modo edición activo"); resumeRun();
};
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("tokenbar").hidden) { closeTokenbar(); $("keyBtn").focus(); } });

let toastTimer;
function toast(msg, ms = 2800) { const t = $("toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), ms); }

// ---------- salud y frescura ----------
function renderHealth() {
  const s = DATA.salud || {}, last = ts(s.ultima_corrida), mac = ts(s.ultima_mac || (/(mac)/i.test(s.fuente || "") ? s.ultima_corrida : null));
  const stale = !last || Date.now() - last > STALE_H * 36e5, macOff = !mac || Date.now() - mac > STALE_H * 36e5;
  const dot = $("healthdot"); dot.classList.toggle("stale", stale && !(s.fallidas_seguidas >= 3)); dot.classList.toggle("down", s.fallidas_seguidas >= 3);
  $("freshtxt").innerHTML = `<span class="long">Buscado </span>${fstamp(s.ultima_corrida)}<span class="long"> · ${s.fallidas_seguidas ? s.fallidas_seguidas + " fallas seguidas" : "sin fallas"}</span>`;
  const note = $("staleNote");
  if (stale) {
    note.hidden = false;
    note.innerHTML = `<b>Precios de hace ${last ? ago(last) : "un rato"}.</b><span>${macOff ? "La Mac de Victor no ha buscado desde " + (mac ? fstamp(s.ultima_mac || s.ultima_corrida) : "hace días") + "; probablemente está apagada. El respaldo de GitHub busca cada 3 horas." : "La última búsqueda tardó más de lo normal."}</span>`;
  } else note.hidden = true;
  const sp = s.serpapi_mes;
  if (view === "editor" && sp && sp.usadas) {
    const now = new Date(), dim = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const proj = Math.round(sp.usadas / now.getDate() * dim), lim = sp.limite || 250;
    $("budgetNote").hidden = proj <= lim;
    $("budgetNote").textContent = `SerpApi: van ${sp.usadas} de ${lim} búsquedas este mes; a este ritmo llegarías a unas ${proj}. Con menos de 30 libres, GitHub solo usa SerpApi cuando tú aprietas Buscar ahora.`;
  } else $("budgetNote").hidden = true;
  const src = esc(s.fuente || "Mac de Victor (Google Flights vía fast-flights)");
  $("foot").innerHTML = `<span>Última búsqueda: ${src}${s.corridas_total ? `, ${s.corridas_total.toLocaleString("en-US")} búsquedas desde el ${fday(s.desde.slice(0, 10))}` : ""}</span><span>Respaldo y botón: GitHub Actions</span><span>Precios con impuestos y TUA, sin maletas ni asiento</span>`;
}

function renderAll() {
  if (!DATA) return;
  renderAnswer(); renderMatrix(); renderHist(); renderOpts(); renderHealth(); renderSavebar();
  const why = needsSearch();
  $("needSearch").hidden = !why.length;
  $("needSearch").textContent = why.length ? `Estos totales usan precios viejos: ${why.join("; ")}. ${view === "editor" ? "Guarda y busca para tener los reales." : ""}` : "";
}

// ---------- carga ----------
function clearAnswer() {
  $("stack").innerHTML = ""; $("tfill").style.width = "0"; $("tmax").textContent = ""; $("legend").innerHTML = ""; $("histfoot").innerHTML = "";
  $("chart").querySelector("svg")?.remove(); $("chart").querySelector(".fail-msg")?.remove();
}
function renderLoading() {
  $("app").classList.add("loading"); clearAnswer();
  if (!$("chart").querySelector(".ph")) $("chart").insertAdjacentHTML("afterbegin", `<div class="ph"></div>`);
  let h = `<div class="h"></div>` + `<div class="h col"><span class="bar-s" style="width:36px;height:12px"></span></div>`.repeat(4);
  for (let i = 0; i < 4; i++) h += `<div class="h rowh"><span class="bar-s" style="width:36px;height:12px"></span></div>` + `<div class="cell ph"></div>`.repeat(4);
  $("mx").style.setProperty("--cols", 4); $("mx").innerHTML = h;
  $("legs").innerHTML = `<div class="leg"><i></i><div><span class="bar-s" style="width:60%;height:14px"></span></div><div class="p"><span class="bar-s" style="width:64px;height:14px"></span></div></div>`.repeat(3);
  $("table").innerHTML = "<tbody>" + `<tr><td><span class="bar-s" style="width:120px;height:14px"></span></td><td class="r"><span class="bar-s" style="width:70px;height:14px"></span></td></tr>`.repeat(5) + "</tbody>";
}
function renderLoadError() {
  clearAnswer(); $("app").classList.remove("loading");
  $("mx").innerHTML = ""; $("table").innerHTML = ""; $("chart").querySelector(".ph")?.remove();
  $("legend").textContent = "Sin precios que mostrar todavía.";
  document.querySelector(".target").hidden = true;
  $("freshtxt").textContent = "Sin datos";
  $("healthdot").classList.add("down");
  $("ansTitle").textContent = "Mejor combinación";
  $("ansTotal").textContent = "—"; $("ansFacts").textContent = ""; $("verdict").textContent = "";
  $("legs").innerHTML = `<div class="fail-msg"><b>No se pudieron cargar los precios.</b><span>Revisa tu conexión.</span><button type="button" class="linkbtn" id="retryBtn">Reintentar</button></div>`;
  $("retryBtn").onclick = () => { renderLoading(); start(); };
}
function applyData(d, conf) {
  DATA = d; latest = d.latest || {}; hist = d.historial || {};
  days = [...new Set(Object.values(hist).flatMap(h => Object.keys(h)))].sort();
  const used = d.config || conf;
  searched = { adultos: used.adultos, xn: (used.grupo_cdmx || {}).adultos || 0, xaps: (used.grupo_cdmx || {}).aeropuertos || [] };
  if (conf) { const keep = cfg && base && dirty(); base = conf; if (!keep) cfg = clone(conf); }
  else if (!base) { base = clone(used); cfg = clone(used); }
}
async function load({ quiet = false } = {}) {
  const [d, conf] = await Promise.all([fetchData(), fetchConfig()]);
  applyData(d, conf);
  $("app").classList.remove("loading");
  fillForm(); renderAll();
}
async function start() {
  renderLoading();
  if (token) {
    const err = await checkToken(token);
    if (err && !/conexión/.test(err)) { forgetToken(); openTokenbar("El token guardado ya no sirve. " + err); }
    else view = "editor";
  }
  try { await load(); } catch (e) { renderLoadError(); return; }
  setView(view);
  if (view === "editor") resumeRun();
}
// Recarga en silencio cada 10 min mientras la pestaña está visible; si falla, se quedan los datos en pantalla.
setInterval(() => { if (document.visibilityState === "visible" && DATA && !running && !busy && !dirty()) load({ quiet: true }).catch(() => toast(`No se pudieron recargar los precios; ves los de ${fstamp(DATA.salud?.ultima_corrida)}.`)); }, 10 * 60e3);
let rz; addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => DATA && renderHist(), 120); });
start();
})();
