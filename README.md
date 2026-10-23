# flight_search_page — sketch

Página para GitHub Pages del monitor de vuelos Puebla/CDMX ⇄ Mérida (dic 2026).
Destino: repo `SMVictorOrtiz/flight_search_page`.

## Qué hay aquí

| Archivo | Qué es |
|---|---|
| `index.html` | El sketch completo. Ábrelo con doble clic: trae los datos embebidos (snapshot del 22 oct 23:07). Buscar y Guardar están simulados. |
| `data/data.json` | Los mismos datos por separado: precios actuales, historial diario por tramo, config y salud del monitor. Es el formato que la Mac subiría al repo. |
| `PRODUCT.md` | Registro de producto (skill impeccable): usuarios, reglas, restricciones. |
| `.impeccable/` | Dirección de diseño elegida ("huipil yucateco") y la tirada de la skill. |

## El monitor NO vive aquí

El scraper sigue en `~/vuelos-monitor` (launchd `mx.victor.vuelos-pbc-mid`).
No lo muevas a Documentos: macOS bloquea a los procesos en segundo plano dentro de
Documentos/Escritorio/Descargas y dejaría de buscar.

## Pendiente para pasar a producción

1. Dar acceso al repo (claude.ai → Settings → Connectors → GitHub).
2. Cambiar el JSON embebido de `index.html` por `fetch("data/data.json")`.
3. Workflow `.github/workflows/buscar.yml` (workflow_dispatch + respaldo con SerpApi).
4. Que `vuelos.py` exporte `data/data.json` y haga `git push` al terminar cada corrida.
5. Decidir: repo privado + GitHub Pro (US$4/mes) o repo público.
