"""
Lectura y escritura del repo por la Contents API de GitHub (sin clone, sin git).

Token: GITHUB_TOKEN en Actions; en la Mac, ~/vuelos-monitor/.github_token (chmod 600).
Sin token se puede leer (el repo es público), pero no publicar.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import stat
import time
import urllib.error
import urllib.request
from pathlib import Path

from exportar import fusionar

REPO = os.environ.get("VUELOS_REPO", "SMVictorOrtiz/flight_search_page")
RAMA = os.environ.get("VUELOS_RAMA", "main")
API = f"https://api.github.com/repos/{REPO}/contents/"
log = logging.getLogger("vuelos")


class Conflicto(Exception):
    """El archivo cambió en el repo entre la lectura y la escritura (sha viejo)."""


def leer_token(base: Path) -> str | None:
    t = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if t:
        return t.strip()
    p = base / ".github_token"
    if not p.exists():
        return None
    if p.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        log.warning("%s se puede leer por otros usuarios; corre: chmod 600 %s", p, p)
    return p.read_text(encoding="utf-8").strip() or None


def _pedir(metodo: str, ruta: str, token: str | None, cuerpo: dict | None = None) -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "vuelos-monitor"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(API + ruta, data=data, method=metodo, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:300]
        if e.code == 409 or (e.code == 422 and "sha" in detalle):
            raise Conflicto(detalle)
        raise RuntimeError(f"GitHub {e.code} en {metodo} {ruta}: {detalle}")


def leer(ruta: str, token: str | None) -> tuple[dict | None, str | None]:
    """(contenido JSON, sha) del archivo en la rama; (None, None) si no existe."""
    try:
        f = _pedir("GET", f"{ruta}?ref={RAMA}", token)
    except RuntimeError as e:
        if "GitHub 404" in str(e):
            return None, None
        raise
    contenido = f.get("content")
    if not contenido and f.get("download_url"):  # > 1 MB: la API no trae el contenido inline
        with urllib.request.urlopen(f["download_url"], timeout=30) as r:
            return json.load(r), f["sha"]
    return json.loads(base64.b64decode(contenido).decode("utf-8")), f["sha"]


def escribir(ruta: str, contenido: str, sha: str | None, mensaje: str, token: str) -> str:
    cuerpo = {"message": mensaje, "content": base64.b64encode(contenido.encode("utf-8")).decode(),
              "branch": RAMA}
    if sha:
        cuerpo["sha"] = sha
    return _pedir("PUT", ruta, token, cuerpo)["content"]["sha"]


def config_remota(base: Path, token: str | None) -> dict | None:
    """config.json del repo (lo que editas en la página). Si no hay red, la última copia buena."""
    cache = base / "datos" / "config.remota.json"
    try:
        cfg, _ = leer("config.json", token)
        if cfg:
            cache.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            return cfg
    except Exception as e:
        log.warning("No pude leer config.json del repo (%s); uso la última copia.", e)
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    return None


def data_remota(token: str | None) -> dict | None:
    try:
        d, _ = leer("data/data.json", token)
        return d
    except Exception as e:
        log.warning("No pude leer data.json del repo: %s", e)
        return None


def publicar(local: dict, token: str, mensaje: str, intentos: int = 6) -> dict:
    """Fusiona con el data.json del repo y lo sube con su sha; si alguien publicó en medio, reintenta."""
    for i in range(intentos):
        remoto, sha = leer("data/data.json", token)
        final = fusionar(remoto, local)
        texto = json.dumps(final, ensure_ascii=False, separators=(",", ":"))
        try:
            escribir("data/data.json", texto, sha, mensaje, token)
            return final
        except Conflicto:
            log.info("data.json cambió en el repo mientras publicaba; reintento (%d/%d)", i + 1, intentos)
            time.sleep(2 + 2 * i)
    raise RuntimeError("No pude publicar data.json: siguió cambiando en el repo")
