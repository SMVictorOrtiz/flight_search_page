/**
 * Worker de Vuelos Mérida: guarda el token de GitHub y solo deja hacer dos cosas a quien sepa la contraseña:
 * guardar las reglas del viaje (validadas) y lanzar una búsqueda. Nunca devuelve el token.
 *
 * Secretos (wrangler secret put): GITHUB_TOKEN, CLAVE, SESION_SECRETO.
 *
 *   POST /sesion   {clave}            → {sesion, vence}
 *   GET  /config                      → {config, sha}
 *   PUT  /config   {config, sha}      → {config, sha}   | 409 {error, config, sha} si cambió en el repo
 *   POST /buscar                      → {desde}
 *   GET  /run[?desde=ISO|?id=N]       → {run: {id, status, conclusion, html_url, created_at, paso} | null}
 */
const WORKFLOW = "buscar.yml";
const SESION_DIAS = 30;

export default {
  async fetch(req, env) {
    const origen = req.headers.get("Origin") || "";
    const permitidos = (env.ORIGENES || "").split(",").map((s) => s.trim()).filter(Boolean);
    const cors = permitidos.includes(origen)
      ? { "Access-Control-Allow-Origin": origen, "Vary": "Origin" }
      : {};
    if (req.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: { ...cors,
        "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "86400" } });
    }
    const responder = (cuerpo, status = 200) => new Response(JSON.stringify(cuerpo), {
      status, headers: { ...cors, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" } });

    try {
      const url = new URL(req.url);
      const ruta = `${req.method} ${url.pathname}`;
      if (ruta === "POST /sesion") return await iniciarSesion(req, env, responder);
      if (!(await sesionValida(req, env))) return responder({ error: "Sesión vencida o inválida" }, 401);
      if (ruta === "GET /config") return responder(await leerConfig(env));
      if (ruta === "PUT /config") return await guardarConfig(req, env, responder);
      if (ruta === "POST /buscar") return await buscar(env, responder);
      if (ruta === "GET /run") return responder({ run: await estadoRun(env, url.searchParams) });
      return responder({ error: "No existe" }, 404);
    } catch (e) {
      return responder({ error: e.publico || "Error del servidor" }, e.status || 500);
    }
  },
};

// ---------------------------------------------------------------- sesión
const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const texto = (s) => new TextEncoder().encode(s);

async function firmar(env, datos) {
  // La llave depende de la contraseña: cambiarla invalida todas las sesiones abiertas.
  const llave = await crypto.subtle.importKey("raw", texto(`${env.SESION_SECRETO}\u0000${env.CLAVE}`),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", llave, texto(datos)));
}

async function iguales(a, b) {
  const [ha, hb] = await Promise.all([crypto.subtle.digest("SHA-256", texto(a)), crypto.subtle.digest("SHA-256", texto(b))]);
  return crypto.subtle.timingSafeEqual(ha, hb);
}

async function iniciarSesion(req, env, responder) {
  const ip = req.headers.get("CF-Connecting-IP") || "sin-ip";
  if (env.INTENTOS) {
    const { success } = await env.INTENTOS.limit({ key: ip });
    if (!success) return responder({ error: "Demasiados intentos" }, 429);
  }
  const { clave } = await req.json().catch(() => ({}));
  if (typeof clave !== "string" || !env.CLAVE || !(await iguales(clave, env.CLAVE))) {
    await new Promise((r) => setTimeout(r, 700));
    return responder({ error: "Contraseña incorrecta" }, 401);
  }
  const vence = Date.now() + SESION_DIAS * 864e5;
  const datos = b64url(texto(JSON.stringify({ vence })));
  return responder({ sesion: `${datos}.${await firmar(env, datos)}`, vence });
}

async function sesionValida(req, env) {
  const m = (req.headers.get("Authorization") || "").match(/^Bearer ([\w-]+)\.([\w-]+)$/);
  if (!m) return false;
  if (!(await iguales(m[2], await firmar(env, m[1])))) return false;
  try {
    const { vence } = JSON.parse(atob(m[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof vence === "number" && vence > Date.now();
  } catch { return false; }
}

// ---------------------------------------------------------------- GitHub
async function gh(env, ruta, { method = "GET", body } = {}) {
  const r = await fetch(`https://api.github.com/repos/${env.REPO}${ruta}`, {
    method,
    headers: { "Authorization": `Bearer ${env.GITHUB_TOKEN}`, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "vuelos-merida-worker" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 204) return null;
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const e = new Error(`GitHub ${r.status}`);
    e.status = r.status === 409 || r.status === 422 ? 409 : 502;
    e.publico = r.status === 401 || r.status === 403 ? "El token del Worker ya no sirve o no tiene permisos" : `GitHub respondió ${r.status}`;
    throw e;
  }
  return data;
}

const desde64 = (s) => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\s/g, "")), (c) => c.charCodeAt(0)));
const a64 = (s) => { let bin = ""; texto(s).forEach((b) => bin += String.fromCharCode(b)); return btoa(bin); };

async function leerConfig(env) {
  const f = await gh(env, "/contents/config.json?ref=main");
  return { config: JSON.parse(desde64(f.content)), sha: f.sha };
}

// ---------------------------------------------------------------- reglas del viaje
const FECHA = /^\d{4}-\d{2}-\d{2}$/;
function invalido(msg) { const e = new Error(msg); e.status = 422; e.publico = msg; throw e; }
function entero(v, min, max, nombre) {
  if (!Number.isInteger(v) || v < min || v > max) invalido(`${nombre} debe ser un número entre ${min} y ${max}`);
  return v;
}
function fecha(v, nombre) {
  if (typeof v !== "string" || !FECHA.test(v) || isNaN(Date.parse(v))) invalido(`${nombre} no es una fecha válida`);
  return v;
}

/** Solo estas llaves se pueden cambiar desde la página; el resto de config.json se conserva tal cual. */
function validar(c) {
  if (!c || typeof c !== "object") invalido("Faltan las reglas");
  const out = {
    adultos: entero(c.adultos, 1, 9, "Desde Puebla"),
    ida_centro: fecha(c.ida_centro, "Ida central"),
    vuelta_centro: fecha(c.vuelta_centro, "Vuelta central"),
    flex_dias: entero(c.flex_dias, 0, 5, "Margen"),
    noches_min: entero(c.noches_min, 1, 20, "Noches mínimo"),
    noches_max: entero(c.noches_max, 1, 20, "Noches máximo"),
    umbral_total_mxn: entero(c.umbral_total_mxn, 0, 1_000_000, "Meta total"),
    costo_equipaje_por_persona_tramo: entero(c.costo_equipaje_por_persona_tramo ?? 0, 0, 10_000, "Maletas"),
  };
  if (out.noches_min > out.noches_max) invalido("Noches mínimo no puede ser mayor que el máximo");
  if (out.vuelta_centro <= out.ida_centro) invalido("La vuelta central debe ser después de la ida");
  for (const k of ["excluir_ida", "excluir_vuelta"]) {
    const v = c[k] ?? [];
    if (!Array.isArray(v) || v.length > 10) invalido("Fechas excluidas inválidas");
    out[k] = v.map((f) => fecha(f, "Fecha excluida"));
  }
  const alt = c.aeropuertos_alternos ?? {};
  if (typeof alt !== "object" || Object.keys(alt).length > 4) invalido("Aeropuertos alternos inválidos");
  out.aeropuertos_alternos = {};
  for (const [ap, costo] of Object.entries(alt)) {
    if (!/^[A-Z]{3}$/.test(ap)) invalido(`Aeropuerto inválido: ${ap}`);
    out.aeropuertos_alternos[ap] = entero(costo, 0, 10_000, `Camión a ${ap}`);
  }
  const x = c.grupo_cdmx ?? {};
  if (x.adultos) {
    const aps = Array.isArray(x.aeropuertos) ? x.aeropuertos : [];
    if (!aps.length || aps.some((a) => !["MEX", "NLU"].includes(a))) invalido("El 4º necesita MEX, NLU o ambos");
    out.grupo_cdmx = { adultos: entero(x.adultos, 1, 4, "Personas desde CDMX"), aeropuertos: [...new Set(aps)],
                       cada_horas: entero(x.cada_horas ?? 1, 1, 24, "Frecuencia del 4º") };
  } else {
    out.grupo_cdmx = {};
  }
  return out;
}

async function guardarConfig(req, env, responder) {
  const { config, sha } = await req.json().catch(() => ({}));
  const limpia = validar(config);
  const actual = await leerConfig(env);
  if (sha && sha !== actual.sha) return responder({ error: "config.json cambió en el repo", ...actual }, 409);
  const nueva = { ...actual.config, ...limpia };
  try {
    const r = await gh(env, "/contents/config.json", { method: "PUT", body: {
      message: "config: reglas del viaje desde la página", branch: "main", sha: actual.sha,
      content: a64(JSON.stringify(nueva, null, 2) + "\n") } });
    return responder({ config: nueva, sha: r.content.sha });
  } catch (e) {
    if (e.status === 409) return responder({ error: "config.json cambió en el repo", ...(await leerConfig(env)) }, 409);
    throw e;
  }
}

// ---------------------------------------------------------------- búsqueda
async function buscar(env, responder) {
  const desde = new Date(Date.now() - 15_000).toISOString();
  await gh(env, `/actions/workflows/${WORKFLOW}/dispatches`, { method: "POST", body: { ref: "main" } });
  return responder({ desde }, 202);
}

/** 0 en cola · 1 buscando · 2 publicando · 3 terminado (los pasos de buscar.yml se llaman "Buscar vuelos" y "Publicar datos"). */
async function paso(env, run) {
  if (run.status === "completed") return 3;
  if (run.status !== "in_progress") return 0;
  const { jobs = [] } = await gh(env, `/actions/runs/${run.id}/jobs`);
  const pasos = jobs.flatMap((j) => j.steps || []);
  const pub = pasos.find((s) => /publicar/i.test(s.name));
  if (pub && pub.status !== "queued") return 2;
  return pasos.some((s) => /buscar/i.test(s.name) && s.status !== "queued") ? 1 : 0;
}

async function estadoRun(env, q) {
  let run = null;
  if (q.get("id")) {
    run = await gh(env, `/actions/runs/${encodeURIComponent(q.get("id"))}`);
  } else if (q.get("desde")) {
    const { workflow_runs = [] } = await gh(env, `/actions/workflows/${WORKFLOW}/runs?event=workflow_dispatch&per_page=5`);
    run = workflow_runs.find((r) => r.created_at >= q.get("desde").slice(0, 19)) || null;
  } else {
    ({ workflow_runs: [run = null] = [] } = await gh(env, `/actions/workflows/${WORKFLOW}/runs?per_page=1`));
  }
  if (!run) return null;
  return { id: run.id, status: run.status, conclusion: run.conclusion, html_url: run.html_url,
           created_at: run.created_at, paso: await paso(env, run) };
}
