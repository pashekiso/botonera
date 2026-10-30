#!/bin/bash
# instalar.command — instala (o actualiza) la Botonera en ~/dev/botonera y, si quieres, mac_health.
#
#   bash instalar.command              # Botonera
#   bash instalar.command --con-salud  # Botonera + mac_health (monitor del Mac, cada hora)
#
# Variables opcionales: BOTONERA_HOME (destino), BOTONERA_PYTHON (intérprete), BOTONERA_PUERTO (8790).
# Se puede repetir para actualizar: conserva config.json y las fichas que tú agregues.
set -euo pipefail

ORIGEN="$(cd "$(dirname "$0")" && pwd)"
DESTINO="${BOTONERA_HOME:-$HOME/dev/botonera}"
PUERTO="${BOTONERA_PUERTO:-8790}"

echo "== Botonera: instalación =="
echo "   origen : $ORIGEN"
echo "   destino: $DESTINO"

PY="${BOTONERA_PYTHON:-}"
if [ -z "$PY" ]; then
  for c in /opt/homebrew/opt/python@3.13/bin/python3.13 python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PY="$(command -v "$c")"; break
    fi
  done
fi
[ -n "$PY" ] || { echo "ERROR: necesito Python 3.9 o superior"; exit 1; }
echo "   python : $PY ($("$PY" -V 2>&1))"

mkdir -p "$DESTINO/estados" "$DESTINO/servicios" "$DESTINO/var"
cp "$ORIGEN/botonera/botonera.py" "$ORIGEN/botonera/puertos.py" "$ORIGEN/botonera/pagina.html" "$DESTINO/"
cp "$ORIGEN/botonera/estados/comun.py" "$ORIGEN/botonera/estados/ejemplo_launchd.py" "$DESTINO/estados/"
cp "$ORIGEN/README.md" "$DESTINO/LEEME.md"
if [ ! -f "$DESTINO/config.json" ]; then
  printf '{\n  "puerto": %s,\n  "registro": "%s/servicios"\n}\n' "$PUERTO" "$DESTINO" > "$DESTINO/config.json"
fi
cat > "$DESTINO/iniciar_botonera.command" <<EOF
#!/bin/bash
# Abre la botonera: deja esta ventana abierta mientras la uses (cerrarla la detiene).
cd "$DESTINO" && exec "$PY" "$DESTINO/botonera.py" servir --abrir
EOF
chmod +x "$DESTINO/iniciar_botonera.command"
"$PY" "$DESTINO/botonera.py" fichas >/dev/null
echo "   ficha propia escrita en $DESTINO/servicios/botonera.json"

if [ "${1:-}" = "--con-salud" ]; then
  MH="${MAC_HEALTH_HOME:-$HOME/dev/mac_health}"
  mkdir -p "$MH"
  cp "$ORIGEN/mac_health/mac_health.py" "$ORIGEN/mac_health/instalar.command" "$ORIGEN/mac_health/LEEME.md" "$MH/"
  chmod +x "$MH/instalar.command"
  echo "== mac_health =="
  BOTONERA_HOME="$DESTINO" "$PY" "$MH/mac_health.py" instalar
fi

echo
echo "Listo. Abre la Botonera con doble clic en: $DESTINO/iniciar_botonera.command"
echo "Para sumar tus propios servicios: docs/CONECTAR.md y fichas-ejemplo/."
