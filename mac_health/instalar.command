#!/bin/bash
# Instala mac_health: agente launchd cada hora + ficha en la Botonera (+ espejo para tu asistente de IA si existe la carpeta).
# Doble clic en Finder o: bash ~/dev/mac_health/instalar.command
cd "$(dirname "$0")" || exit 1
PY="/opt/homebrew/opt/python@3.13/bin/python3.13"
[ -x "$PY" ] || PY="$(command -v python3)"
"$PY" "$(pwd)/mac_health.py" instalar
echo
echo "Listo. Abre la Botonera (~/dev/botonera/iniciar_botonera.command): la tarjeta 'OSHealth' aparece en la próxima actualización."
read -r -p "Enter para cerrar…" _
