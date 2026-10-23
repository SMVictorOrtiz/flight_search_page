# Vuelos Mérida

Monitor de precios del viaje Puebla/CDMX ⇄ Mérida (diciembre 2026), publicado en GitHub Pages.
El grupo solo ve la página; quien tiene el token en su navegador puede cambiar las reglas y lanzar búsquedas.

## Cómo está armado

```
Mac (launchd, IP de casa)          GitHub Actions (respaldo + botón)
~/vuelos-monitor/vuelos.py          engine/vuelos.py
        │                                   │
        └──── PUT data/data.json ───────────┘   ← fusión: nunca se sobrescribe
                    (Contents API, con sha)
                         │
                index.html lee data.json por la API (fresco) o de Pages (respaldo)
                y escribe config.json con el token del navegador
```

| Archivo | Qué es |
|---|---|
| `index.html`, `assets/` | La página. HTML/CSS/JS sin build. |
| `config.json` | Reglas del viaje. Lo edita la página; la Mac y Actions lo leen al empezar cada corrida. **Sin secretos.** |
| `data/data.json` | Precios actuales (`latest`), historial diario por tramo, salud del monitor. Lo escriben la Mac y Actions. |
| `engine/` | El motor: `vuelos.py` (búsqueda), `exportar.py` (arma y fusiona data.json), `sincronizar.py` (API de GitHub). |
| `.github/workflows/buscar.yml` | Botón "Buscar ahora" y respaldo cada 3 h. |

## El motor vive en dos lugares, a propósito

macOS no deja que launchd lea Documentos, así que la Mac ejecuta una **copia** del motor en
`~/vuelos-monitor`. La fuente de verdad es `engine/` en este repo:

1. Cambia el código en `engine/` y haz commit.
2. Cópialo a la Mac desde Terminal (Terminal sí puede leer Documentos):

   ```bash
   bash engine/sync-mac.sh
   ```

El script respalda lo anterior en `~/vuelos-monitor/respaldos/`, saca los secretos de `config.json` a
`config.local.json` y muestra la huella del motor. `data.json` guarda la huella de la Mac y la de Actions
(`salud.motor`): si no coinciden, a alguno le falta el último cambio.

## Secretos (el repo es público)

| Dónde | Qué |
|---|---|
| `~/vuelos-monitor/config.local.json` (Mac) | `serpapi_key`, `ntfy_topic`, `pushover_*`, preferencias de alertas de la Mac |
| `~/vuelos-monitor/.github_token` (Mac, `chmod 600`) | Token fine-grained para publicar `data.json` |
| GitHub → Settings → Secrets → Actions | `SERPAPI_KEY` y, si quieres alertas desde CI, `NTFY_TOPIC`, `PUSHOVER_USER_KEY`, `PUSHOVER_APP_TOKEN` |
| `localStorage` del navegador de Victor | El mismo tipo de token, para guardar reglas y lanzar búsquedas |

El token: GitHub → Settings → Developer settings → Fine-grained tokens → solo el repo
`SMVictorOrtiz/flight_search_page`, permisos **Contents: Read and write** y **Actions: Read and write**.

## Fusión de data.json

La Mac y Actions leen el `data.json` del repo antes de buscar y otra vez antes de publicar:

- **historial**: el mínimo por `direccion|aeropuerto|fecha` y día.
- **latest**: gana el `cuando` más reciente, salvo que después se buscó y ya no había vuelo (`sin_vuelo`).
  Se descartan fechas y aeropuertos que ya no entran en las reglas.
- **salud**: corridas sumadas por lado (`corridas.mac`, `corridas.ci`), `ultima_mac`, `ultima_ci`, gasto de SerpApi del mes.
- **mínimo histórico / última alerta**: el menor total y la alerta más reciente (así no avisan los dos).

El PUT lleva el `sha` leído; si alguien publicó en medio, vuelve a leer, fusiona y reintenta.

## SerpApi

Plan gratis: 250 búsquedas al mes entre la Mac y Actions. Actions usa como máximo 12 por corrida, solo en
fechas que ya se sabe que tienen vuelo, y cuando quedan 30 o menos solo las usa si apretaste "Buscar ahora".
La página avisa en "Reglas del viaje" si a este ritmo el mes se va a pasar.

## Comandos

```bash
cd ~/vuelos-monitor
.venv/bin/python vuelos.py                  # corrida + publicar (lo que hace launchd)
.venv/bin/python vuelos.py --exportar /tmp/data.json   # ver qué se publicaría
.venv/bin/python vuelos.py --solo-publicar  # volver a publicar sin buscar
python3 -m unittest discover -s engine      # pruebas de la fusión (desde el repo)
```

## Probar la página en local

```bash
python3 -m http.server 8765
```

Abre http://localhost:8765. Lee los datos reales del repo por la API.
