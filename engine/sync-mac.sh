#!/bin/bash
# Copia el motor del repo (engine/) a ~/vuelos-monitor, donde launchd sí lo puede ejecutar.
# macOS no deja que launchd lea Documentos, así que el código vive en el repo y se copia desde Terminal.
# Uso (desde la raíz del repo):  bash engine/sync-mac.sh
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${VUELOS_DEST:-$HOME/vuelos-monitor}"
ARCHIVOS=(vuelos.py exportar.py sincronizar.py)

[ -d "$DEST" ] || { echo "❌ No existe $DEST. Instala primero el monitor (instalar.sh)."; exit 1; }

# 1) Respaldo de lo que había y copia del motor
STAMP="$(date +%Y%m%d-%H%M)"
mkdir -p "$DEST/respaldos"
for f in "${ARCHIVOS[@]}"; do
  if [ -f "$DEST/$f" ] && ! cmp -s "$SRC/$f" "$DEST/$f"; then
    cp -p "$DEST/$f" "$DEST/respaldos/$f.$STAMP"
  fi
  cp "$SRC/$f" "$DEST/$f"
done
echo "📦 Motor copiado a $DEST (respaldos en $DEST/respaldos/)"

# 2) Secretos fuera de config.json: van a config.local.json (nunca al repo)
"$DEST/.venv/bin/python" - "$DEST" <<'EOF'
import json, sys
from pathlib import Path
base = Path(sys.argv[1])
cfg_p, loc_p = base / "config.json", base / "config.local.json"
LOCALES = ["ntfy_topic", "pushover_user_key", "pushover_app_token", "serpapi_key",
           "pushover_emergencia", "alerta_mac_sonido", "alerta_mac_ventana"]
cfg = json.loads(cfg_p.read_text(encoding="utf-8")) if cfg_p.exists() else {}
loc = json.loads(loc_p.read_text(encoding="utf-8")) if loc_p.exists() else {}
movidos = [k for k in LOCALES if k in cfg]
for k in movidos:
    loc.setdefault(k, cfg.pop(k))
if movidos or not loc_p.exists():
    loc_p.write_text(json.dumps(loc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    loc_p.chmod(0o600)
    cfg_p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"🔐 {len(movidos)} campos movidos de config.json a config.local.json")
EOF

# 3) Token para publicar data.json
TOKEN="$DEST/.github_token"
if [ -s "$TOKEN" ]; then
  chmod 600 "$TOKEN"
  echo "🔑 Token encontrado ($TOKEN, chmod 600)"
else
  echo "⚠️  Falta $TOKEN: la Mac seguirá buscando pero no publicará data.json."
  echo "    Pega el token fine-grained ahí y corre:  chmod 600 $TOKEN"
fi

# 4) Huella: debe coincidir con la de GitHub Actions (la página la muestra si difieren)
cd "$DEST" && "$DEST/.venv/bin/python" -c "import vuelos; print('🧬 Huella del motor:', vuelos.huella_motor())" 2>/dev/null | tail -1
