"""
Arma data/data.json (lo que lee la página) desde busquedas_*.csv + combinaciones_*.csv + estado.json,
y fusiona dos snapshots sin perder nada: la Mac y GitHub Actions publican al mismo archivo.

Formato:
  generado, config (sin secretos), salud, minimo_historico, ultima_alerta, latest, historial,
  mejor_total_diario_3p  (+ minimo_historico_4p, ultima_alerta_4p, sin_vuelo como extras)
"""
from __future__ import annotations

import csv
import copy
from datetime import date, datetime
from pathlib import Path

# Nunca salen de la máquina: el repo es público.
SECRETOS = {"ntfy_topic", "pushover_user_key", "pushover_app_token", "serpapi_key"}
SOLO_MAC = {"alerta_mac_sonido", "alerta_mac_ventana", "pushover_emergencia"}
# Campos del caché que la página no usa (y que hacían más pesado el JSON)
FUERA_DE_LATEST = {"escalas", "de_nombre", "a_nombre", "fuente"}
EXTRAS_ESTADO = ("minimo_historico", "ultima_alerta", "minimo_historico_4p", "ultima_alerta_4p")


def config_publica(cfg: dict) -> dict:
    return {k: v for k, v in cfg.items() if k not in SECRETOS | SOLO_MAC and not k.startswith("_")}


def _filas(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        hdr = next(r, None)
        for row in r:
            if row:
                yield hdr, row


def historial(datos: Path) -> dict:
    """Mínimo diario por 'direccion|aeropuerto|fecha', de todas las busquedas_*.csv con ese formato."""
    h: dict[str, dict[str, int]] = {}
    for path in sorted(datos.glob("busquedas*.csv")):
        for hdr, row in _filas(path):
            if "aeropuerto" not in hdr:
                continue  # el CSV v1 no tenía aeropuerto
            fila = dict(zip(hdr, row))
            if not fila.get("precio_total_min"):
                continue
            k = f"{fila['direccion']}|{fila['aeropuerto']}|{fila['fecha_vuelo']}"
            dia, p = fila["timestamp"][:10], int(float(fila["precio_total_min"]))
            h.setdefault(k, {})
            h[k][dia] = min(p, h[k].get(dia, p))
    return {k: dict(sorted(v.items())) for k, v in sorted(h.items())}


def mejor_total_diario(datos: Path) -> dict:
    """Mejor total del grupo de Puebla (vuelos + camión) por día, de combinaciones_v2/v3."""
    m: dict[str, int] = {}
    for path in sorted(datos.glob("combinaciones_v*.csv")):
        for hdr, row in _filas(path):
            if "total_grupo_puebla" in hdr:
                v = row[hdr.index("total_grupo_puebla")]
            elif "total_3_personas" in hdr:
                v = row[-2]  # v2 ganó una columna (maletas) a media vida; el total siempre es la penúltima
            else:
                continue
            if v:
                dia = row[0][:10]
                m[dia] = min(int(float(v)), m.get(dia, 10**9))
    return dict(sorted(m.items()))


def corridas(datos: Path) -> tuple[int, str | None]:
    """(número de corridas, primera) contadas como timestamps distintos en busquedas_v2.csv."""
    ts = {row[0] for _, row in _filas(datos / "busquedas_v2.csv")}
    return len(ts), (min(ts) if ts else None)


def armar(cfg: dict, estado: dict, datos: Path, lado: str, fuente: str, motor: str) -> dict:
    n, desde = corridas(datos)
    sp = estado.get("serpapi_mes") or {}
    salud = {
        "ultima_corrida": estado.get("ultima_corrida"),
        "fallidas_seguidas": estado.get("corridas_fallidas_seguidas", 0),
        "corridas_total": n + estado.get("corridas_base", 0),
        "desde": estado.get("desde_base") or desde,
        "fuente": fuente,
        f"ultima_{lado}": estado.get("ultima_corrida"),
        "corridas": {lado: n + estado.get("corridas_base", 0)},
        "serpapi_mes": {"mes": sp.get("mes"), lado: sp.get("usadas", 0),
                        "limite": cfg.get("serpapi_limite_mes", 250)},
        "motor": {lado: motor},
    }
    out = {
        "generado": datetime.now().isoformat(timespec="minutes"),
        "config": config_publica(cfg),
        "salud": salud,
        "minimo_historico": estado.get("minimo_historico"),
        "ultima_alerta": estado.get("ultima_alerta"),
        "latest": {k: {c: v for c, v in x.items() if c not in FUERA_DE_LATEST}
                   for k, x in sorted((estado.get("cache") or {}).items())},
        "historial": historial(datos),
        "mejor_total_diario_3p": mejor_total_diario(datos),
    }
    for k in ("minimo_historico_4p", "ultima_alerta_4p"):
        if estado.get(k):
            out[k] = estado[k]
    if estado.get("sin_vuelo"):
        out["sin_vuelo"] = estado["sin_vuelo"]
    return out


# ---------------------------------------------------------------- fusión
def clave_valida(cfg: dict, k: str) -> bool:
    """Misma regla con la que la corrida limpia su caché: fechas en rango y aeropuertos vigentes."""
    try:
        dirn, ap, f = k.split("|")
    except ValueError:
        return False
    flex = cfg.get("flex_dias", 0)
    centro = cfg["ida_centro"] if dirn.startswith("ida") else cfg["vuelta_centro"]
    excl = cfg.get("excluir_ida" if dirn.startswith("ida") else "excluir_vuelta", [])
    if f in excl or abs((date.fromisoformat(f) - date.fromisoformat(centro)).days) > flex:
        return False
    if dirn.endswith("_cdmx"):
        x = cfg.get("grupo_cdmx") or {}
        return bool(x.get("adultos")) and ap in x.get("aeropuertos", [])
    return ap == cfg["origen"] or ap in (cfg.get("aeropuertos_alternos") or {})


def _menor(a, b, campo="total"):
    if not a or not b:
        return a or b
    return a if a[campo] <= b[campo] else b


def _reciente(a, b, campo="cuando"):
    if not a or not b:
        return a or b
    return a if (a.get(campo) or "") >= (b.get(campo) or "") else b


def _fusionar_salud(r: dict, l: dict) -> dict:
    cr = dict(r.get("corridas") or {"mac": r.get("corridas_total", 0)}) if r else {}
    for lado, n in (l.get("corridas") or {}).items():
        cr[lado] = max(cr.get(lado, 0), n)
    nueva = _reciente(l, r, "ultima_corrida")
    out = {
        "ultima_corrida": max(filter(None, [r.get("ultima_corrida"), l.get("ultima_corrida")]), default=None),
        "fallidas_seguidas": nueva.get("fallidas_seguidas", 0),
        "corridas_total": sum(cr.values()),
        "desde": min(filter(None, [r.get("desde"), l.get("desde")]), default=None),
        "fuente": nueva.get("fuente"),
        "corridas": cr,
    }
    for lado in ("mac", "ci"):
        v = max(filter(None, [r.get(f"ultima_{lado}"), l.get(f"ultima_{lado}")]), default=None)
        if lado == "mac" and v is None and "mac" in (r.get("fuente") or "").lower():
            v = r.get("ultima_corrida")  # snapshot viejo, de antes de separar Mac y CI
        if v:
            out[f"ultima_{lado}"] = v
    sr, sl = r.get("serpapi_mes") or {}, l.get("serpapi_mes") or {}
    if (sr.get("mes") or "") > (sl.get("mes") or ""):
        sp = dict(sr)
    elif (sl.get("mes") or "") > (sr.get("mes") or ""):
        sp = dict(sl)
    else:
        sp = {**sr, **sl}
        for lado in ("mac", "ci"):
            sp[lado] = max(sr.get(lado, 0), sl.get(lado, 0))
    sp["usadas"] = sp.get("mac", 0) + sp.get("ci", 0)
    out["serpapi_mes"] = sp
    out["motor"] = {**(r.get("motor") or {}), **(l.get("motor") or {})}
    return out


def fusionar(remoto: dict | None, local: dict) -> dict:
    """Une el data.json del repo con el recién armado. Historial: mínimo por llave y día.
    latest: el 'cuando' más reciente, salvo que después se buscó y ya no había vuelo."""
    if not remoto:
        local = copy.deepcopy(local)
        local["salud"] = _fusionar_salud({}, local["salud"])
        return local
    out = copy.deepcopy(local)

    h = copy.deepcopy(remoto.get("historial") or {})
    for k, dias in local.get("historial", {}).items():
        hk = h.setdefault(k, {})
        for d, v in dias.items():
            hk[d] = min(v, hk.get(d, v))
    out["historial"] = {k: dict(sorted(v.items())) for k, v in sorted(h.items())}

    m = dict(remoto.get("mejor_total_diario_3p") or {})
    for d, v in local.get("mejor_total_diario_3p", {}).items():
        m[d] = min(v, m.get(d, v))
    out["mejor_total_diario_3p"] = dict(sorted(m.items()))

    sv = dict(remoto.get("sin_vuelo") or {})
    for k, t in (local.get("sin_vuelo") or {}).items():
        sv[k] = max(t, sv.get(k, t))
    lat = {}
    for fuente in (remoto.get("latest") or {}, local.get("latest") or {}):
        for k, v in fuente.items():
            lat[k] = _reciente(v, lat.get(k)) if k in lat else v
    cfg = local["config"]
    out["latest"] = {k: v for k, v in sorted(lat.items())
                     if clave_valida(cfg, k) and sv.get(k, "") <= (v.get("cuando") or "")}
    sv = {k: t for k, t in sv.items() if clave_valida(cfg, k)}
    if sv:
        out["sin_vuelo"] = dict(sorted(sv.items()))
    else:
        out.pop("sin_vuelo", None)

    for k in ("minimo_historico", "minimo_historico_4p"):
        v = _menor(remoto.get(k), local.get(k))
        if v:
            out[k] = v
    for k in ("ultima_alerta", "ultima_alerta_4p"):
        v = _reciente(remoto.get(k), local.get(k))
        if v:
            out[k] = v
    out["salud"] = _fusionar_salud(remoto.get("salud") or {}, local["salud"])
    return out
