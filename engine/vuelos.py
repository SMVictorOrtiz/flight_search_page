#!/usr/bin/env python3
"""
Monitor de precios de vuelos Puebla/CDMX <-> Mérida para 3 adultos.

Uso:
  python vuelos.py                 # una corrida normal (lo que ejecuta launchd)
  python vuelos.py --top           # muestra el último TOP 3 con detalles
  python vuelos.py --probar        # prueba: 1 vs 3 adultos y con/sin equipaje
  python vuelos.py --probar-alertas
  python vuelos.py --analizar      # ¿a qué hora sale más barato? (usa tu historial)
  python vuelos.py --estado        # mínimo histórico, última alerta, etc.
  python vuelos.py --solo-buscar   # corrida sin publicar (GitHub Actions publica en otro paso)
  python vuelos.py --solo-publicar # arma data.json y lo sube al repo
  python vuelos.py --exportar F    # arma data.json en el archivo F, sin publicar
  python vuelos.py --reciente H    # imprime "si" si la última corrida publicada tiene menos de H horas

Fuente principal: Google Flights vía la librería `fast-flights` (gratis, no oficial).
Respaldo: SerpApi (oficial, 250 búsquedas/mes gratis) con serpapi_key en config.local.json
o el secret SERPAPI_KEY en GitHub.

Configuración, de menor a mayor prioridad:
  DEFAULTS → config.json local (copia de respaldo) → config.json del repo (lo que editas en la página)
  → config.local.json (secretos y preferencias de esta Mac) → variables de entorno (secrets de CI).

Este archivo vive en el repo (engine/) y se copia a ~/vuelos-monitor con engine/sync-mac.sh.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import itertools
import json
import logging
import os
import random
import re
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

CODIGO = Path(__file__).resolve().parent
sys.path.insert(0, str(CODIGO))
import exportar  # noqa: E402
import sincronizar  # noqa: E402

# En la Mac todo vive junto al script; en GitHub Actions, VUELOS_HOME apunta a una carpeta temporal.
BASE = Path(os.environ.get("VUELOS_HOME") or CODIGO)
EN_CI = os.environ.get("GITHUB_ACTIONS") == "true"
LADO = "ci" if EN_CI else "mac"
CONFIG = BASE / "config.json"
CONFIG_LOCAL = BASE / "config.local.json"
DATA = BASE / "datos"
LOGS = BASE / "logs"
ESTADO = DATA / "estado.json"
CSV_BUSQUEDAS = DATA / "busquedas_v2.csv"
CSV_COMBOS = DATA / "combinaciones_v3.csv"
TOP_TXT = DATA / "top3.txt"
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

DEFAULTS = {
    "origen": "PBC",
    "destino": "MID",
    "adultos": 3,
    "solo_directos": True,
    "ida_centro": "2026-12-22",
    "vuelta_centro": "2026-12-29",
    "flex_dias": 2,
    "noches_min": 5,
    "noches_max": 9,
    "excluir_ida": [],
    "excluir_vuelta": [],
    "aeropuertos_alternos": {},          # {"MEX": 480, "NLU": 545}  -> costo traslado por persona, por sentido
    "alternos_cada_horas": 2,
    # Integrante(s) que salen y regresan a CDMX, mismas fechas que el grupo, sin camión:
    # {"adultos": 1, "aeropuertos": ["MEX", "NLU"], "cada_horas": 1}   ({} = desactivado)
    "grupo_cdmx": {},
    "equipaje_mano": 0,                  # 0/1: pide a Google el precio con maleta de mano incluida
    "maletas_documentadas": 0,           # 0/1/2
    "costo_equipaje_por_persona_tramo": 0,  # MXN que cobra la aerolínea por tus maletas (lo sumamos nosotros)
    "top_n": 3,
    "umbral_total_mxn": 12000,
    "realertar_si_baja_mxn": 300,
    "realertar_cada_horas": 12,
    "ntfy_topic": "",
    "pushover_user_key": "",
    "pushover_app_token": "",
    "pushover_emergencia": True,
    "alerta_mac_sonido": True,
    "alerta_mac_ventana": True,
    "serpapi_key": "",
    "serpapi_max_por_dia": 8,
    "serpapi_limite_mes": 250,           # plan gratis de SerpApi, sumando Mac + GitHub Actions
    "serpapi_max_por_corrida_ci": 12,
    "serpapi_reserva_manual": 30,        # con tan pocas libres, CI solo usa SerpApi si apretaste "Buscar ahora"
    "pausa_entre_busquedas_seg": [4, 9],
    # GitHub Actions: consultas en paralelo con pausa corta. La Mac sigue de una en una (cuida la IP de casa).
    "hilos_ci": 4,
    "pausa_ci_seg": [1.5, 3.5],
}
# Secretos que en CI llegan como variables de entorno (GitHub Secrets)
SECRETOS_ENV = {"serpapi_key": "SERPAPI_KEY", "ntfy_topic": "NTFY_TOPIC",
                "pushover_user_key": "PUSHOVER_USER_KEY", "pushover_app_token": "PUSHOVER_APP_TOKEN"}

DATA.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOGS / "monitor.log"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("vuelos")
# El cliente HTTP de fast-flights imprime cada URL en INFO; lo bajamos a WARNING para un log legible
for _n in ("primp", "rquest", "hyper", "httpx"):
    logging.getLogger(_n).setLevel(logging.WARNING)


class FuenteError(Exception):
    """La fuente falló (bloqueo, red, cambio en Google). Distinto de 'no hay vuelos'."""


# ---------------------------------------------------------------- utilidades
def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def cargar_config(remota: bool = True) -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(_json(CONFIG))
    if remota:
        r = sincronizar.config_remota(BASE, sincronizar.leer_token(BASE))
        if r:
            cfg.update(r)
    cfg.update(_json(CONFIG_LOCAL))
    for k, env in SECRETOS_ENV.items():
        if os.environ.get(env):
            cfg[k] = os.environ[env]
    return cfg


def huella_motor() -> str:
    h = hashlib.sha256()
    for nombre in ("vuelos.py", "exportar.py", "sincronizar.py"):
        h.update((CODIGO / nombre).read_bytes())
    return h.hexdigest()[:8]


def importar_remoto(estado: dict, remoto: dict | None) -> None:
    """Trae al estado local lo que publicó el otro lado (Mac o CI): precios más nuevos,
    mínimos, última alerta (para no avisar dos veces) y el gasto de SerpApi del mes."""
    if not remoto:
        return
    cache = estado.setdefault("cache", {})
    for k, v in (remoto.get("latest") or {}).items():
        if (v.get("cuando") or "") > (cache.get(k, {}).get("cuando") or ""):
            cache[k] = {"escalas": 0, "de_nombre": "", "a_nombre": "", "fuente": "repo", **v}
    sv = estado.setdefault("sin_vuelo", {})
    for k, t in (remoto.get("sin_vuelo") or {}).items():
        sv[k] = max(t, sv.get(k, t))
        if k in cache and (cache[k].get("cuando") or "") < sv[k]:
            del cache[k]
    con_vuelo = set(estado.get("dias_con_vuelo", [])) | set(remoto.get("latest") or {}) | set(remoto.get("historial") or {})
    estado["dias_con_vuelo"] = sorted(con_vuelo)
    for k in ("minimo_historico", "minimo_historico_4p"):
        a, b = estado.get(k), remoto.get(k)
        if b and (not a or b["total"] < a["total"]):
            estado[k] = b
    for k in ("ultima_alerta", "ultima_alerta_4p"):
        a, b = estado.get(k), remoto.get(k)
        if b and (not a or b["cuando"] > a["cuando"]):
            estado[k] = b
    salud = remoto.get("salud") or {}
    sp_r, mes = salud.get("serpapi_mes") or {}, date.today().strftime("%Y-%m")
    sp = estado.setdefault("serpapi_mes", {"mes": mes, "usadas": 0})
    if sp.get("mes") != mes:
        sp.update(mes=mes, usadas=0)
    if sp_r.get("mes") == mes:
        sp["usadas"] = max(sp["usadas"], sp_r.get(LADO, 0))
        sp["otros"] = sum(v for k2, v in sp_r.items() if k2 in ("mac", "ci") and k2 != LADO)
    if EN_CI:  # CI no guarda nada entre corridas: su contador y su "desde" viven en data.json
        estado["corridas_base"] = (salud.get("corridas") or {}).get("ci", 0)
        estado["desde_base"] = salud.get("desde")


def cargar_estado() -> dict:
    if ESTADO.exists():
        try:
            return json.loads(ESTADO.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("estado.json corrupto; se reinicia")
    return {}


def guardar_estado(e: dict) -> None:
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ESTADO)


def rango_fechas(centro: str, flex: int, excluir: list[str]) -> list[str]:
    c = date.fromisoformat(centro)
    hoy = date.today()
    out = []
    for d in range(-flex, flex + 1):
        f = c + timedelta(d)
        if f >= hoy and f.isoformat() not in excluir:
            out.append(f.isoformat())
    return out


def grupo_cdmx(cfg: dict) -> tuple[int, list[str]]:
    """(adultos, aeropuertos) del integrante que sale de CDMX; (0, []) si está desactivado.
    Sin aeropuertos no hay nada que buscar ni sumar: cuenta como desactivado."""
    x = cfg.get("grupo_cdmx") or {}
    n = int(x.get("adultos", 0) or 0)
    aps = list(x.get("aeropuertos", []))
    return (n, aps) if n and aps else (0, [])


def personas(cfg: dict) -> int:
    return cfg["adultos"] + grupo_cdmx(cfg)[0]


def mxn(n: float | int | None) -> str:
    return "—" if n is None else f"${n:,.0f}"


def fecha_corta(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month]}"


def append_csv(path: Path, fila: dict) -> None:
    nuevo = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fila.keys()))
        if nuevo:
            w.writeheader()
        w.writerow(fila)


def texto_equipaje(cfg: dict) -> str:
    partes = ["artículo personal"]
    if cfg["equipaje_mano"]:
        partes.append("maleta de mano")
    if cfg["maletas_documentadas"]:
        partes.append(f"{cfg['maletas_documentadas']} documentada(s)")
    return " + ".join(partes)


# ---------------------------------------------------------------- Google (fast-flights)
def _g(x, *idx):
    """Acceso seguro a listas anidadas: _g(a, 1, 0, 2) -> a[1][0][2] o None."""
    for i in idx:
        if not isinstance(x, list) or i >= len(x):
            return None
        x = x[i]
    return x


def _hhmm(v) -> str:
    v = [*(v or []), None, None]
    return "%02d:%02d" % (v[0] or 0, v[1] or 0)


def _numero_vuelo(seg) -> str:
    """Busca algo como ['VB', '1234', ...] dentro del segmento (Google no documenta la posición)."""
    candidatos = [_g(seg, 22)] + [x for x in (seg or []) if isinstance(x, list)]
    for c in candidatos:
        if (isinstance(c, list) and len(c) >= 2 and isinstance(c[0], str) and len(c[0]) == 2
                and isinstance(c[1], str) and c[1].isdigit()):
            return f"{c[0]} {c[1]}"
    return ""


def parsear_google(html: str, url: str) -> list[dict]:
    m = re.search(r"<script[^>]*class=\"ds:1\"[^>]*>(.*?)</script>", html, re.S)
    if not m:
        if "consent.google" in html or "Antes de ir a Google" in html or "Before you continue" in html:
            raise FuenteError("Google pidió aceptar cookies (página de consentimiento)")
        if "unusual traffic" in html or "tráfico inusual" in html or "/sorry/" in html:
            raise FuenteError("Google detectó tráfico inusual (captcha); baja la frecuencia")
        raise FuenteError("la página no trae el bloque de datos ds:1")
    js = m.group(1)
    if "data:" not in js:
        raise FuenteError("bloque ds:1 sin datos")
    data = js.split("data:", 1)[1].rsplit(",", 1)[0].strip()
    if data.endswith("errorHasStatus: true"):
        return []
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as e:
        raise FuenteError(f"JSON inválido: {e}")

    out, vistos = [], set()
    # payload[2][0] = "mejores vuelos", payload[3][0] = "otros vuelos" (cualquiera puede venir vacío)
    for bloque in (_g(payload, 2, 0), _g(payload, 3, 0)):
        for k in bloque or []:
            flight, precio = _g(k, 0), _g(k, 1, 0, 1)
            segs = _g(flight, 2) or []
            if not segs or not isinstance(precio, (int, float)):
                continue
            s0, sN = segs[0], segs[-1]
            dep_d, arr_d = _g(s0, 20), _g(sN, 21)
            mas1 = isinstance(dep_d, list) and isinstance(arr_d, list) and arr_d != dep_d
            dur = sum(x for x in (_g(s, 11) for s in segs) if isinstance(x, int))
            item = {
                "precio_total": int(precio),  # Google: total de TODOS los pasajeros, con impuestos y TUA
                "aerolinea": ", ".join(_g(flight, 1) or []),
                "vuelo": " / ".join(filter(None, (_numero_vuelo(s) for s in segs))),
                "escalas": len(segs) - 1,
                "de": _g(s0, 3) or "", "de_nombre": _g(s0, 4) or "",
                "a": _g(sN, 6) or "", "a_nombre": _g(sN, 5) or "",
                "salida": _hhmm(_g(s0, 8)),
                "llegada": _hhmm(_g(sN, 10)) + (" (+1)" if mas1 else ""),
                "duracion_min": dur,
                "avion": _g(s0, 17) or "",
                "link": url,
                "fuente": "google",
            }
            clave = (item["precio_total"], item["salida"], item["vuelo"])
            if clave not in vistos:
                vistos.add(clave)
                out.append(item)
    return out


def buscar_fast_flights(cfg: dict, origen: str, destino: str, fecha: str, adultos: int,
                        con_equipaje: bool = True) -> list[dict]:
    try:
        from fast_flights import FlightQuery, Passengers, create_query, fetch_flights_html
    except ImportError as e:  # pragma: no cover
        raise FuenteError(f"fast-flights no instalado: {e}")

    q = create_query(
        flights=[FlightQuery(date=fecha, from_airport=origen, to_airport=destino)],
        trip="one-way",
        seat="economy",
        passengers=Passengers(adults=adultos),
        currency="MXN",
        language="es",
        max_stops=0 if cfg["solo_directos"] else None,
        carry_on_bags=cfg["equipaje_mano"] if con_equipaje else 0,
        checked_bags=cfg["maletas_documentadas"] if con_equipaje else 0,
    )
    url = q.url()
    try:
        html = fetch_flights_html(q)
    except Exception as e:
        raise FuenteError(f"descarga: {type(e).__name__}: {str(e)[:200]}")
    try:
        res = parsear_google(html, url)
    except FuenteError:
        dump = LOGS / f"google_{origen}{destino}_{fecha}.html"
        dump.write_text(html, encoding="utf-8")
        log.warning("No pude leer la respuesta de Google; guardada en %s", dump)
        raise
    for r in res:
        r["equipaje"] = texto_equipaje(cfg) if con_equipaje else "artículo personal (sin maletas)"
    return res


# ---------------------------------------------------------------- SerpApi (respaldo)
def buscar_serpapi(cfg: dict, origen: str, destino: str, fecha: str, adultos: int,
                   con_equipaje: bool = True) -> list[dict]:
    params = {
        "engine": "google_flights", "departure_id": origen, "arrival_id": destino,
        "outbound_date": fecha, "type": "2", "adults": str(adultos),
        "currency": "MXN", "hl": "es", "gl": "mx", "api_key": cfg["serpapi_key"],
    }
    if cfg["solo_directos"]:
        params["stops"] = "1"
    if con_equipaje and cfg["equipaje_mano"]:
        params["bags"] = str(cfg["equipaje_mano"] * adultos)
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = json.load(r)
    except Exception as e:
        raise FuenteError(f"SerpApi: {e}")
    if "error" in data:
        if "hasn't returned any results" in data["error"]:
            return []
        raise FuenteError(f"SerpApi: {data['error']}")

    out = []
    for f in data.get("best_flights", []) + data.get("other_flights", []):
        segs = f.get("flights") or []
        if not segs or not f.get("price"):
            continue
        s0, sN = segs[0], segs[-1]
        out.append({
            "precio_total": int(f["price"]),
            "aerolinea": ", ".join(dict.fromkeys(s.get("airline", "") for s in segs)),
            "vuelo": " / ".join(s.get("flight_number", "") for s in segs),
            "escalas": len(segs) - 1,
            "de": s0["departure_airport"].get("id", ""), "de_nombre": s0["departure_airport"].get("name", ""),
            "a": sN["arrival_airport"].get("id", ""), "a_nombre": sN["arrival_airport"].get("name", ""),
            "salida": s0["departure_airport"]["time"][-5:],
            "llegada": sN["arrival_airport"]["time"][-5:],
            "duracion_min": f.get("total_duration", 0),
            "avion": s0.get("airplane", ""),
            "link": data.get("search_metadata", {}).get("google_flights_url", ""),
            "fuente": "serpapi",
            "equipaje": texto_equipaje(cfg) if con_equipaje else "artículo personal (sin maletas)",
        })
    return out


# ---------------------------------------------------------------- alertas
def alerta_mac(cfg: dict, titulo: str, mensaje: str) -> None:
    if sys.platform != "darwin":
        log.info("(no es macOS, se omite alerta local) %s | %s", titulo, mensaje)
        return
    script = ["-e", "on run argv",
              "-e", 'display notification (item 2 of argv) with title (item 1 of argv) sound name "Glass"',
              "-e", "end run"]
    subprocess.run(["osascript", *script, titulo, mensaje], check=False)
    if cfg.get("alerta_mac_sonido"):
        subprocess.Popen(["/bin/sh", "-c",
                          "for i in 1 2 3; do afplay /System/Library/Sounds/Sosumi.aiff; sleep 0.4; done"])
    if cfg.get("alerta_mac_ventana"):
        subprocess.Popen(["osascript", "-e", "on run argv",
                          "-e", "display alert (item 1 of argv) message (item 2 of argv) as critical giving up after 21600",
                          "-e", "end run", titulo, mensaje])


def alerta_ntfy(cfg: dict, titulo: str, mensaje: str, link: str) -> None:
    topic = cfg.get("ntfy_topic")
    if not topic:
        return
    body = json.dumps({"topic": topic, "title": titulo, "message": mensaje, "priority": 5,
                       "tags": ["airplane", "rotating_light"], "click": link}).encode()
    req = urllib.request.Request("https://ntfy.sh/", data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20).read()
        log.info("ntfy enviado")
    except Exception as e:
        log.error("ntfy falló: %s", e)


def alerta_pushover(cfg: dict, titulo: str, mensaje: str, link: str) -> None:
    if not (cfg.get("pushover_user_key") and cfg.get("pushover_app_token")):
        return
    datos = {"token": cfg["pushover_app_token"], "user": cfg["pushover_user_key"],
             "title": titulo, "message": mensaje[:1000], "url": link[:500],
             "url_title": "Ver en Google Flights", "sound": "siren"}
    if cfg.get("pushover_emergencia", True):
        datos.update({"priority": "2", "retry": "60", "expire": "3600"})
    else:
        datos["priority"] = "1"
    req = urllib.request.Request("https://api.pushover.net/1/messages.json",
                                 data=urllib.parse.urlencode(datos).encode())
    try:
        urllib.request.urlopen(req, timeout=20).read()
        log.info("Pushover enviado")
    except Exception as e:
        log.error("Pushover falló: %s", e)


def enviar_alertas(cfg: dict, titulo: str, mensaje: str, link: str) -> None:
    alerta_mac(cfg, titulo, mensaje)
    alerta_ntfy(cfg, titulo, mensaje, link)
    alerta_pushover(cfg, titulo, mensaje, link)


# ---------------------------------------------------------------- búsqueda
class Buscador:
    def __init__(self, cfg: dict, estado: dict):
        self.cfg, self.estado = cfg, estado
        self.fast_ok = True
        hoy = date.today().isoformat()
        sp = estado.setdefault("serpapi", {})
        if sp.get("fecha") != hoy:
            sp.update(fecha=hoy, usadas=0)
        self.sp = sp
        mes = date.today().strftime("%Y-%m")
        self.mes = estado.setdefault("serpapi_mes", {"mes": mes, "usadas": 0})
        if self.mes.get("mes") != mes:
            self.mes.update(mes=mes, usadas=0, otros=0)
        self.en_corrida = 0
        self.fuentes: set[str] = set()
        self.candado = threading.Lock()  # contadores de SerpApi compartidos entre hilos
        self.pausa = cfg["pausa_ci_seg"] if EN_CI else cfg["pausa_entre_busquedas_seg"]

    def serpapi_libres(self) -> int:
        return self.cfg["serpapi_limite_mes"] - self.mes["usadas"] - self.mes.get("otros", 0)

    def _serpapi_permitida(self, prioridad_alta: bool) -> bool:
        if not self.cfg.get("serpapi_key") or self.serpapi_libres() <= 0:
            return False
        if EN_CI:
            manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
            return (prioridad_alta and self.en_corrida < self.cfg["serpapi_max_por_corrida_ci"]
                    and (manual or self.serpapi_libres() > self.cfg["serpapi_reserva_manual"]))
        return (self.sp["usadas"] < self.cfg["serpapi_max_por_dia"]
                and (prioridad_alta or self.sp["usadas"] < self.cfg["serpapi_max_por_dia"] // 2))

    def _una(self, o, d, fecha, prioridad_alta, con_equipaje, adultos):
        if self.fast_ok:
            try:
                res = buscar_fast_flights(self.cfg, o, d, fecha, adultos, con_equipaje)
                self.fuentes.add("fast-flights")
                return res, "google"
            except FuenteError as e:
                log.warning("fast-flights falló (%s). Se usa respaldo el resto de esta corrida.", e)
                self.fast_ok = False
        with self.candado:
            permitida = self._serpapi_permitida(prioridad_alta)
            if permitida:
                self.sp["usadas"] += 1
                self.mes["usadas"] += 1
                self.en_corrida += 1
                self.fuentes.add("SerpApi")
        if permitida:
            try:
                return buscar_serpapi(self.cfg, o, d, fecha, adultos, con_equipaje), "serpapi"
            except FuenteError as e:
                log.error("%s", e)
        return None, "sin-fuente"

    def buscar(self, o, d, fecha, conocido_con_vuelo: bool, adultos: int | None = None):
        """Busca con equipaje; si no sale nada en un día que sabemos que sí tiene vuelo,
        reintenta sin equipaje (Google oculta vuelos cuando no conoce el costo de la maleta)."""
        adultos = adultos or self.cfg["adultos"]
        pide_maletas = bool(self.cfg["equipaje_mano"] or self.cfg["maletas_documentadas"])
        res, fuente = self._una(o, d, fecha, conocido_con_vuelo, True, adultos)
        if res is not None and self.cfg["solo_directos"]:
            res = [x for x in res if x["escalas"] == 0]
        if res == [] and pide_maletas and conocido_con_vuelo:
            time.sleep(random.uniform(*self.pausa))
            res2, fuente = self._una(o, d, fecha, conocido_con_vuelo, False, adultos)
            if res2:
                res = [x for x in res2 if x["escalas"] == 0] if self.cfg["solo_directos"] else res2
                for x in res:
                    x["equipaje"] += " ⚠️ Google no tenía el costo de la maleta"
        return res, fuente


def corrida() -> int:
    cfg = cargar_config()
    estado = cargar_estado()
    importar_remoto(estado, sincronizar.data_remota(sincronizar.leer_token(BASE)))
    ahora = datetime.now()
    b = Buscador(cfg, estado)
    try:
        return _corrida(cfg, estado, ahora, b)
    finally:
        quien = "GitHub Actions" if EN_CI else "Mac"
        estado["fuente"] = f"{quien} ({' + '.join(sorted(b.fuentes)) or 'sin fuente'})"
        avisar_presupuesto_serpapi(cfg, b)
        guardar_estado(estado)


def avisar_presupuesto_serpapi(cfg: dict, b: "Buscador") -> None:
    usadas = b.mes["usadas"] + b.mes.get("otros", 0)
    if not usadas:
        return
    hoy = date.today()
    dias_mes = ((hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day
    proyeccion = round(usadas / hoy.day * dias_mes)
    if proyeccion > cfg["serpapi_limite_mes"]:
        msg = (f"SerpApi: van {usadas} de {cfg['serpapi_limite_mes']} búsquedas este mes; "
               f"a este ritmo llegarías a ~{proyeccion}.")
        log.warning(msg)
        if EN_CI:
            print(f"::warning title=SerpApi::{msg}")


def _corrida(cfg: dict, estado: dict, ahora: datetime, b: "Buscador") -> int:
    # (migra el formato viejo "ida:2026-12-22" -> "ida|PBC|2026-12-22")
    con_vuelo = {k.replace(":", f"|{cfg['origen']}|", 1) if ":" in k else k
                 for k in estado.get("dias_con_vuelo", [])}
    cache = estado.setdefault("cache", {})  # clave "dir|aeropuerto|fecha" -> mejor opción (+ cuando)

    alternos = cfg["aeropuertos_alternos"] or {}
    ult_alt = estado.get("ultima_busqueda_alternos")
    toca_alternos = bool(alternos) and (
        ult_alt is None
        or (ahora - datetime.fromisoformat(ult_alt)).total_seconds() / 3600 >= cfg["alternos_cada_horas"] - 0.1)

    x_n, x_aps = grupo_cdmx(cfg)
    ult_x = estado.get("ultima_busqueda_cdmx")
    toca_cdmx = bool(x_aps) and (
        ult_x is None
        or (ahora - datetime.fromisoformat(ult_x)).total_seconds() / 3600
        >= (cfg.get("grupo_cdmx") or {}).get("cada_horas", 1) - 0.1)

    ida_fechas = rango_fechas(cfg["ida_centro"], cfg["flex_dias"], cfg["excluir_ida"])
    vta_fechas = rango_fechas(cfg["vuelta_centro"], cfg["flex_dias"], cfg["excluir_vuelta"])
    aeropuertos = [cfg["origen"]] + (list(alternos) if toca_alternos else [])

    tareas = []
    for ap in aeropuertos:
        tareas += [("ida", ap, ap, cfg["destino"], f, cfg["adultos"]) for f in ida_fechas]
        tareas += [("vuelta", ap, cfg["destino"], ap, f, cfg["adultos"]) for f in vta_fechas]
    if toca_cdmx:  # integrante de CDMX: mismas fechas, búsqueda con SUS adultos (no se divide el precio de 3)
        for ap in x_aps:
            tareas += [("ida_cdmx", ap, ap, cfg["destino"], f, x_n) for f in ida_fechas]
            tareas += [("vuelta_cdmx", ap, cfg["destino"], ap, f, x_n) for f in vta_fechas]
    # Días que ya sabemos que tienen vuelo, primero (importa si caemos al respaldo)
    tareas.sort(key=lambda t: f"{t[0]}|{t[1]}|{t[4]}" not in con_vuelo)

    def consultar(t):
        direccion, ap, o, d, fecha, n_pax = t
        opciones, fuente = b.buscar(o, d, fecha, f"{direccion}|{ap}|{fecha}" in con_vuelo, n_pax)
        if fuente != "sin-fuente":  # sin fuente no hubo petición: no hace falta esperar
            time.sleep(random.uniform(*b.pausa))
        return t, opciones, fuente

    hilos = max(1, int(cfg["hilos_ci"])) if EN_CI else 1
    if hilos > 1:
        log.info("%d consultas en %d hilos", len(tareas), hilos)
        with ThreadPoolExecutor(hilos) as ex:
            resultados = list(ex.map(consultar, tareas))
    else:
        resultados = map(consultar, tareas)  # perezoso: en la Mac se registra cada consulta al momento

    consultas_ok = 0
    for (direccion, ap, o, d, fecha, n_pax), opciones, fuente in resultados:
        clave = f"{direccion}|{ap}|{fecha}"
        if opciones is None:
            log.info("%-6s %s %s: no se pudo consultar", direccion, ap, fecha)
            continue
        consultas_ok += 1
        top = min(opciones, key=lambda x: x["precio_total"]) if opciones else None
        if top:
            con_vuelo.add(clave)
            cache[clave] = {**top, "cuando": ahora.isoformat(timespec="minutes")}
        else:
            cache.pop(clave, None)
            # Para que la fusión con el repo no resucite un vuelo que ya no existe
            estado.setdefault("sin_vuelo", {})[clave] = ahora.isoformat(timespec="minutes")
        append_csv(CSV_BUSQUEDAS, {
            "timestamp": ahora.isoformat(timespec="minutes"), "hora": ahora.hour,
            "dia_semana_busqueda": DIAS[ahora.weekday()], "direccion": direccion, "aeropuerto": ap,
            "fecha_vuelo": fecha, "dia_vuelo": DIAS[date.fromisoformat(fecha).weekday()],
            "precio_total_min": top["precio_total"] if top else "",
            "precio_por_persona": round(top["precio_total"] / n_pax) if top else "",
            "aerolinea": top["aerolinea"] if top else "", "vuelo": top["vuelo"] if top else "",
            "salida": top["salida"] if top else "", "llegada": top["llegada"] if top else "",
            "equipaje": top["equipaje"] if top else "", "opciones": len(opciones), "fuente": fuente,
        })
        log.info("%-11s %s %s: %s  %s", direccion, ap, fecha_corta(fecha),
                 mxn(top["precio_total"]) if top else "sin directos",
                 f"{top['aerolinea']} {top['vuelo']} {top['salida']}→{top['llegada']}" if top else "")

    if toca_alternos and consultas_ok:
        estado["ultima_busqueda_alternos"] = ahora.isoformat(timespec="minutes")
    if toca_cdmx and consultas_ok:
        estado["ultima_busqueda_cdmx"] = ahora.isoformat(timespec="minutes")
    estado["dias_con_vuelo"] = sorted(con_vuelo)
    # ultima_corrida = última con precios; un intento fallido no debe hacer parecer frescos los datos
    estado["ultimo_intento"] = ahora.isoformat(timespec="minutes")

    if consultas_ok == 0:
        log.error("Ninguna consulta funcionó en esta corrida.")
        fallos = estado.get("corridas_fallidas_seguidas", 0) + 1
        estado["corridas_fallidas_seguidas"] = fallos
        if fallos == 6:
            alerta_mac(cfg, "Monitor de vuelos: sin datos",
                       "Lleva 6 corridas sin poder consultar precios. Revisa logs/monitor.log")
        return 1
    estado["corridas_fallidas_seguidas"] = 0
    estado["ultima_corrida"] = ahora.isoformat(timespec="minutes")

    # Limpia del caché fechas excluidas o fuera de rango (por si cambiaste config.json)
    validas_ida, validas_vta = set(ida_fechas), set(vta_fechas)
    for k in list(cache):
        dirn, ap, f = k.split("|")
        es_cdmx = dirn.endswith("_cdmx")
        base_dir = dirn.removesuffix("_cdmx")
        if ((base_dir == "ida" and f not in validas_ida) or (base_dir == "vuelta" and f not in validas_vta)
                or (not es_cdmx and ap != cfg["origen"] and ap not in alternos)
                or (es_cdmx and ap not in x_aps)):
            del cache[k]

    top = armar_top(cfg, cache)
    if not top:
        log.info("Todavía no hay combinación ida+vuelta que cumpla fechas y noches.")
        return 0

    reporte = formatear_top(cfg, top, ahora)
    TOP_TXT.write_text(reporte, encoding="utf-8")
    log.info("\n%s", reporte)

    mejor = top[0]
    append_csv(CSV_COMBOS, {
        "timestamp": ahora.isoformat(timespec="minutes"), "hora": ahora.hour,
        "dia_semana_busqueda": DIAS[ahora.weekday()],
        "ida_aeropuerto": mejor["ida"]["de"] or mejor["ap_ida"], "fecha_ida": mejor["f_ida"],
        "vuelta_aeropuerto": mejor["vta"]["a"] or mejor["ap_vta"], "fecha_vuelta": mejor["f_vta"],
        "noches": mejor["noches"], "ida_total": mejor["ida"]["precio_total"],
        "vuelta_total": mejor["vta"]["precio_total"], "traslado": mejor["traslado"],
        "maletas": mejor.get("maletas", 0),
        "cdmx_ida": mejor["x_ida"]["precio_total"] if mejor.get("x_ida") else "",
        "cdmx_vuelta": mejor["x_vta"]["precio_total"] if mejor.get("x_vta") else "",
        "total_grupo_puebla": mejor["total_grupo"], "personas": personas(cfg),
        "total": mejor["total"], "por_persona": round(mejor["total"] / personas(cfg)),
    })
    N = personas(cfg)
    suf = "" if N == cfg["adultos"] else f"_{N}p"  # no mezcla el histórico de 3 con el de 4

    historico = estado.get("minimo_historico" + suf)
    if historico is None or mejor["total"] < historico["total"]:
        estado["minimo_historico" + suf] = {"total": mejor["total"], "ida": f"{mejor['ap_ida']} {mejor['f_ida']}",
                                      "vuelta": f"{mejor['ap_vta']} {mejor['f_vta']}",
                                      "cuando": ahora.isoformat(timespec="minutes")}

    total = mejor["total"]
    if total <= cfg["umbral_total_mxn"]:
        ult = estado.get("ultima_alerta" + suf)
        horas = (ahora - datetime.fromisoformat(ult["cuando"])).total_seconds() / 3600 if ult else None
        if (ult is None or total <= ult["total"] - cfg["realertar_si_baja_mxn"]
                or horas >= cfg["realertar_cada_horas"]):
            i, v = mejor["ida"], mejor["vta"]
            titulo = f"✈️ {mxn(total)} para {N} (ida+vuelta)"
            xi, xv = mejor.get("x_ida"), mejor.get("x_vta")
            msg = (f"IDA {fecha_corta(mejor['f_ida'])} {i['de']}→{i['a']} {i['salida']}–{i['llegada']} "
                   f"{i['vuelo']} {mxn(i['precio_total'])}\n"
                   f"VUELTA {fecha_corta(mejor['f_vta'])} {v['de']}→{v['a']} {v['salida']}–{v['llegada']} "
                   f"{v['vuelo']} {mxn(v['precio_total'])}\n"
                   + (f"Traslado CDMX {mxn(mejor['traslado'])}\n" if mejor["traslado"] else "")
                   + (f"+CDMX IDA {xi['de']} {xi['salida']} {xi['vuelo']} {mxn(xi['precio_total'])} · "
                      f"VUELTA →{xv['a']} {xv['salida']} {xv['vuelo']} {mxn(xv['precio_total'])}\n" if xi and xv else "")
                   + (f"Maletas {mxn(mejor['maletas'])}\n" if mejor.get("maletas") else "")
                   + f"{mxn(total / N)} por persona · {mejor['noches']} noches · {i['equipaje']}")
            enviar_alertas(cfg, titulo, msg, i.get("link", ""))
            estado["ultima_alerta" + suf] = {"total": total, "cuando": ahora.isoformat(timespec="minutes")}
    return 0


# ---------------------------------------------------------------- publicar en el repo
def armar_data(cfg: dict | None = None) -> dict:
    cfg = cfg or cargar_config()
    estado = cargar_estado()
    return exportar.armar(cfg, estado, DATA, LADO,
                          estado.get("fuente") or ("GitHub Actions" if EN_CI else "Mac (fast-flights)"),
                          huella_motor())


def publicar() -> int:
    token = sincronizar.leer_token(BASE)
    if not token:
        log.warning("Sin token de GitHub (%s): no se publica data.json.", BASE / ".github_token")
        return 0
    cfg = cargar_config()
    local = armar_data(cfg)
    top = armar_top(cfg, cargar_estado().get("cache", {}))
    mejor = f" — mejor {mxn(top[0]['total'])}" if top else ""
    quien = "CI" if EN_CI else "Mac"
    try:
        cuando = local["salud"].get("ultimo_intento") or local["salud"]["ultima_corrida"]
        final = sincronizar.publicar(local, token, f"datos: corrida {quien} {cuando}{mejor}")
    except Exception as e:
        log.error("No pude publicar data.json: %s", e)
        return 1
    log.info("data.json publicado (%d precios, %d corridas en total)",
             len(final["latest"]), final["salud"]["corridas_total"])
    return 0


def reciente(horas: float) -> bool:
    d = sincronizar.data_remota(sincronizar.leer_token(BASE)) or {}
    ult = (d.get("salud") or {}).get("ultima_corrida")
    if not ult:
        return False
    return (datetime.now() - datetime.fromisoformat(ult)).total_seconds() < horas * 3600


def armar_top(cfg: dict, cache: dict) -> list[dict]:
    alternos = cfg["aeropuertos_alternos"] or {}
    costo = lambda ap: 0 if ap == cfg["origen"] else alternos.get(ap, 0) * cfg["adultos"]
    idas = [(k.split("|")[1], k.split("|")[2], v) for k, v in cache.items() if k.startswith("ida|")]
    vtas = [(k.split("|")[1], k.split("|")[2], v) for k, v in cache.items() if k.startswith("vuelta|")]
    x_n, x_aps = grupo_cdmx(cfg)
    mejor_x = {}  # ("ida_cdmx"|"vuelta_cdmx", fecha) -> vuelo más barato entre sus aeropuertos
    for k, v in cache.items():
        dirn, ap, f = k.split("|")
        if x_n and dirn in ("ida_cdmx", "vuelta_cdmx") and ap in x_aps:
            if (dirn, f) not in mejor_x or v["precio_total"] < mejor_x[(dirn, f)]["precio_total"]:
                mejor_x[(dirn, f)] = v
    combos = []
    for (ap_i, f_i, ida), (ap_v, f_v, vta) in itertools.product(idas, vtas):
        noches = (date.fromisoformat(f_v) - date.fromisoformat(f_i)).days
        if not (cfg["noches_min"] <= noches <= cfg["noches_max"]):
            continue
        x_ida = x_vta = None
        if x_n:
            x_ida, x_vta = mejor_x.get(("ida_cdmx", f_i)), mejor_x.get(("vuelta_cdmx", f_v))
            if not (x_ida and x_vta):
                continue  # sin precio del integrante de CDMX en esas fechas: no se puede comparar
        traslado = costo(ap_i) + costo(ap_v)
        maletas = cfg["costo_equipaje_por_persona_tramo"] * personas(cfg) * 2
        extra = (x_ida["precio_total"] + x_vta["precio_total"]) if x_n else 0
        total_grupo = ida["precio_total"] + vta["precio_total"] + traslado
        combos.append({"ap_ida": ap_i, "f_ida": f_i, "ida": ida, "ap_vta": ap_v, "f_vta": f_v, "vta": vta,
                       "noches": noches, "traslado": traslado, "maletas": maletas,
                       "vuelos": ida["precio_total"] + vta["precio_total"],
                       "x_ida": x_ida, "x_vta": x_vta, "extra": extra, "total_grupo": total_grupo,
                       "total": total_grupo + extra + maletas})
    combos.sort(key=lambda c: c["total"])
    top = combos[: cfg["top_n"]]
    # Siempre muestra también la mejor opción 100% Puebla, aunque no entre al top
    solo_origen = [c for c in combos if c["ap_ida"] == cfg["origen"] and c["ap_vta"] == cfg["origen"]]
    if solo_origen and solo_origen[0] not in top:
        top.append({**solo_origen[0], "etiqueta": f"Mejor opción solo {cfg['origen']}"})
    return top


def link_combinado(cfg: dict, c: dict) -> str:
    """Una sola búsqueda de Google con los dos tramos: redondo si sale y regresa al mismo
    aeropuerto; multidestino si no (p. ej. ida desde AIFA y regreso a Puebla)."""
    try:
        from fast_flights import FlightQuery, Passengers, create_query
        ida_de, ida_a = c["ida"]["de"] or c["ap_ida"], c["ida"]["a"] or cfg["destino"]
        vta_de, vta_a = c["vta"]["de"] or cfg["destino"], c["vta"]["a"] or c["ap_vta"]
        q = create_query(
            flights=[FlightQuery(date=c["f_ida"], from_airport=ida_de, to_airport=ida_a),
                     FlightQuery(date=c["f_vta"], from_airport=vta_de, to_airport=vta_a)],
            trip="round-trip" if (ida_de == vta_a and ida_a == vta_de) else "multi-city",
            seat="economy", passengers=Passengers(adults=cfg["adultos"]),
            currency="MXN", language="es", max_stops=0 if cfg["solo_directos"] else None,
        )
        return q.url()
    except Exception as e:  # el link es un extra; nunca debe tumbar la corrida
        log.debug("sin link combinado: %s", e)
        return ""


def formatear_top(cfg: dict, top: list[dict], ahora: datetime) -> str:
    n = cfg["adultos"]
    x_n, _ = grupo_cdmx(cfg)
    N = n + x_n
    quien = f"{n} desde Puebla + {x_n} desde CDMX" if x_n else f"{n} adultos"
    L = [f"══════ TOP {min(len(top), cfg['top_n'])} COMBINACIONES · {quien} · {ahora:%d/%m %H:%M} ══════",
         f"Precios de vuelo = total de cada grupo, con impuestos y TUA (lo que muestra Google)."
         + (f" TOTAL y 'por persona' incluyen a los {N}." if x_n else "")]
    if not cfg["costo_equipaje_por_persona_tramo"]:
        L.append("⚠️ El TOTAL no incluye maletas: pon su costo en config.json → costo_equipaje_por_persona_tramo.")
    for i, c in enumerate(top, 1):
        L.append("")
        L.append(f"{c.get('etiqueta', '#' + str(i))}  {mxn(c['total'])} TOTAL  ·  {mxn(c['total'] / N)} por persona  ·  {c['noches']} noches"
                 + ("  ✅ bajo tu umbral" if c["total"] <= cfg["umbral_total_mxn"] else ""))
        for etiqueta, f, x in (("IDA   ", c["f_ida"], c["ida"]), ("VUELTA", c["f_vta"], c["vta"])):
            h, m = divmod(x.get("duracion_min") or 0, 60)
            L.append(f"   {etiqueta} {fecha_corta(f):<11} {x['aerolinea']} {x['vuelo']}".rstrip())
            L.append(f"          {x['de']} {x['de_nombre']} {x['salida']}  →  {x['a']} {x['a_nombre']} {x['llegada']}"
                     f"   ({h}h{m:02d}{', ' + x['avion'] if x.get('avion') else ''})")
            L.append(f"          {mxn(x['precio_total'])} ({mxn(x['precio_total'] / n)} c/u) · Equipaje: {x['equipaje']}"
                     f" · visto {x.get('cuando', '')[11:]}")
        if c.get("maletas"):
            L.append(f"   Maletas ({mxn(cfg['costo_equipaje_por_persona_tramo'])} por persona por tramo, dato tuyo): {mxn(c['maletas'])}")
        if c["traslado"]:
            tramos = [ap for ap in (c["ap_ida"], c["ap_vta"]) if ap != cfg["origen"]]
            L.append(f"   Traslado camión Puebla⇄{'/'.join(dict.fromkeys(tramos))} "
                     f"({len(tramos)} {'sentido' if len(tramos) == 1 else 'sentidos'}, {n} pers.): {mxn(c['traslado'])}")
        L.append(f"   Link ida:    {c['ida'].get('link', '')}")
        L.append(f"   Link vuelta: {c['vta'].get('link', '')}")
        combinado = link_combinado(cfg, c)
        if combinado:
            L.append(f"   Link ambos:  {combinado}")
        if c.get("x_ida"):
            L.append(f"   + {x_n} desde CDMX (sin camión):")
            for etiqueta, f, x, grupo in (("IDA   ", c["f_ida"], c["x_ida"], c["ida"]),
                                          ("VUELTA", c["f_vta"], c["x_vta"], c["vta"])):
                juntos = "  ✈️ mismo vuelo que el grupo" if x.get("vuelo") and x["vuelo"] == grupo.get("vuelo") else ""
                L.append(f"     {etiqueta} {x['aerolinea']} {x['vuelo']}  {x['de']} {x['salida']} → {x['a']} {x['llegada']}"
                         f"  ·  {mxn(x['precio_total'])}{juntos} · visto {x.get('cuando', '')[11:]}")
                L.append(f"            {x.get('link', '')}")
            L.append(f"   Subtotal grupo Puebla {mxn(c['total_grupo'])} + CDMX {mxn(c['extra'])}")
    L.append("")
    L.append("No incluido: selección de asiento. Compra en la web de la aerolínea.")
    return "\n".join(L)


# ---------------------------------------------------------------- comandos extra
def analizar() -> None:
    if not CSV_COMBOS.exists():
        print("Aún no hay historial. Deja correr el monitor unos días.")
        return
    filas = list(csv.DictReader(CSV_COMBOS.open(encoding="utf-8")))
    print(f"{len(filas)} mediciones · del {filas[0]['timestamp']} al {filas[-1]['timestamp']}\n")

    def tabla(clave: str, orden: list, etiqueta) -> None:
        g = defaultdict(list)
        for f in filas:
            g[f[clave]].append(int(f.get("total") or f["total_3_personas"]))
        print(f"{'':>6}  {'n':>4}  {'promedio':>10}  {'mínimo':>10}")
        for k in orden:
            if k in g:
                v = g[k]
                print(f"{etiqueta(k):>6}  {len(v):>4}  {mxn(statistics.mean(v)):>10}  {mxn(min(v)):>10}")
        print()

    print("Mejor total (ida+vuelta+traslado, todos) según la HORA en que se buscó:")
    tabla("hora", [str(h) for h in range(24)], lambda h: f"{int(h):02d}:00")
    print("Según el DÍA de la semana en que se buscó:")
    tabla("dia_semana_busqueda", DIAS, lambda d: d)
    print("Ojo: el precio también cambia con los días que faltan para volar. Compara horas dentro\n"
          "de la misma semana antes de concluir que 'la madrugada' es mejor.")


def probar() -> None:
    cfg = cargar_config()
    fechas = rango_fechas(cfg["ida_centro"], cfg["flex_dias"], cfg["excluir_ida"])
    print("Buscando la primera fecha de ida con vuelo directo…")
    for fecha in fechas:
        try:
            base3 = [x for x in buscar_fast_flights(cfg, cfg["origen"], cfg["destino"], fecha, cfg["adultos"], False)
                     if x["escalas"] == 0]
        except FuenteError as e:
            print(f"fast-flights falló: {e}")
            return
        if not base3:
            print(f"  {fecha}: sin directos")
            continue
        base1 = [x for x in buscar_fast_flights(cfg, cfg["origen"], cfg["destino"], fecha, 1, False) if x["escalas"] == 0]
        p3 = min(x["precio_total"] for x in base3)
        p1 = min(x["precio_total"] for x in base1) if base1 else None
        print(f"\n  {fecha}: {cfg['adultos']} adultos = {mxn(p3)} | 1 adulto = {mxn(p1)}")
        if p1:
            r = p3 / p1
            print(f"  Relación: {r:.2f}x → " + ("✅ el precio es TOTAL de los 3" if r > 2 else "⚠️ parece POR PERSONA"))
        if cfg["equipaje_mano"] or cfg["maletas_documentadas"]:
            con = [x for x in buscar_fast_flights(cfg, cfg["origen"], cfg["destino"], fecha, cfg["adultos"], True)
                   if x["escalas"] == 0]
            if con:
                pc = min(x["precio_total"] for x in con)
                print(f"  Con equipaje ({texto_equipaje(cfg)}): {mxn(pc)} → diferencia {mxn(pc - p3)} "
                      f"({mxn((pc - p3) / cfg['adultos'])} por persona)")
            else:
                print("  Con equipaje: Google no devolvió vuelos (no tiene el costo de la maleta de esta aerolínea).")
        print("\n  Detalle del vuelo más barato:")
        for k, v in min(base3, key=lambda x: x["precio_total"]).items():
            print(f"    {k:>13}: {v}")
        return
    print("No encontré directos en ninguna fecha de ida del rango.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--top", action="store_true")
    g.add_argument("--probar", action="store_true")
    g.add_argument("--probar-alertas", action="store_true")
    g.add_argument("--analizar", action="store_true")
    g.add_argument("--estado", action="store_true")
    g.add_argument("--solo-buscar", action="store_true")
    g.add_argument("--solo-publicar", action="store_true")
    g.add_argument("--exportar", metavar="ARCHIVO")
    g.add_argument("--reciente", metavar="HORAS", type=float)
    a = p.parse_args()

    if a.reciente is not None:
        print("si" if reciente(a.reciente) else "no")
        return 0
    if a.exportar:
        Path(a.exportar).write_text(json.dumps(armar_data(), ensure_ascii=False, separators=(",", ":")),
                                    encoding="utf-8")
        print(f"Escrito {a.exportar}")
        return 0
    if a.solo_publicar:
        return publicar()

    if a.top:
        print(TOP_TXT.read_text(encoding="utf-8") if TOP_TXT.exists() else "Aún no hay TOP; corre el monitor.")
        return 0
    if a.analizar:
        analizar(); return 0
    if a.probar:
        probar(); return 0
    if a.estado:
        e = cargar_estado(); e.pop("cache", None)
        print(json.dumps(e, ensure_ascii=False, indent=2)); return 0
    if a.probar_alertas:
        cfg = cargar_config(remota=False)
        enviar_alertas(cfg, "✈️ Prueba monitor de vuelos", "Si ves esto, las alertas funcionan.",
                       "https://www.google.com/travel/flights")
        return 0

    with open(DATA / ".lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log.info("Ya hay una corrida en curso; salgo.")
            return 0
        rc = corrida()
    if a.solo_buscar:
        return rc
    return publicar() or rc


if __name__ == "__main__":
    sys.exit(main())
