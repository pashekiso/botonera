# mac_health — OSHealth (salud del Mac)

Mide cada hora el estado del MacBook, recomienda reiniciar cuando hay señales de degradación y, desde la
Botonera, prepara el equipo para que el reinicio lo deje limpio. Un solo archivo de Python con biblioteca
estándar; la medición la dispara `launchd`, no Claude (cuesta milisegundos y no depende de ninguna sesión).

## Instalar

```bash
bash ~/dev/mac_health/instalar.command
```

Escribe `~/Library/LaunchAgents/local.mac-health.plist` (cada 3600 s y al iniciar sesión), deja la ficha
`~/dev/botonera/servicios/mac_health.json` y crea `~/dev/cowork-local/mac_health/` (espejo de solo lectura
para los Cowork). Hace la primera medición al terminar. Para quitarlo: `python3 mac_health.py desinstalar`.

## Qué mide y cómo decide

| Señal | Fuente | Amarillo | Rojo |
|---|---|---|---|
| Swap usado | `sysctl vm.swapusage` | > 1.5 GB | > 4 GB |
| Tiempo encendido | `sysctl kern.boottime` | > 3 días | > 7 días |
| Presión de memoria | `sysctl kern.memorystatus_vm_pressure_level` | aviso (2) | crítica (4) |
| Pageouts | `vm_stat` (incremento entre lecturas) | > 330 MB en la última hora | creciendo 3 lecturas seguidas |
| Disco libre | `shutil.disk_usage` | < 25 GB | < 10 GB |
| Carga por núcleo | `sysctl vm.loadavg / hw.logicalcpu` | > 1.5 | — |
| Límite térmico CPU | `pmset -g therm` | < 100 % | — |
| Servidores locales de maquetas | `lsof -iTCP -sTCP:LISTEN` | > 5 | — |
| `~/Library/Caches` | `du -sk` | > 10 GB | — |
| `kernel_task` | `ps` | > 30 % CPU | — |

Durante los primeros 10 minutos tras encender ("calentamiento"), la carga y `kernel_task` no se evalúan: la tarjeta queda en gris con "Esperando uptime". Umbral `calentamiento_s`.

Rojo → "Conviene reiniciar: …"; amarillo → "Vigilar: …"; verde → "Sin señales de degradación".
Los umbrales están en el dict `UMBRAL` al inicio de `mac_health.py`.

## La tarjeta en la Botonera

- **Medir ahora**: lectura inmediata (tarda unos segundos por el `du` de Caches).
- **Preparar reinicio** (pide confirmación): corre en segundo plano, el avance se ve en el subtítulo de la
  tarjeta ("Mantención en curso: paso k/13 …") y en **Ver registro**. Pasos, en orden:
  1. `colima stop` y quit de Docker Desktop si están corriendo.
  2. Cierra los servidores que escuchan en localhost, salvo la Botonera, todo lo que viva en `/Applications`,
     `/System` o `/Library`, colima/lima, ssh y los navegadores.
  3. Cierra procesos de pruebas: uvicorn, http.server, vite, streamlit, Playwright/Chrome headless, ngrok…
  4. Pide quit a las apps abiertas, excepto Finder, Terminal, iTerm2, Claude y navegadores. Las que
     queden abiertas (documentos sin guardar) se listan en la tarjeta.
  5. `brew cleanup -s --prune=all`, `npm cache clean --force`, `pip cache purge`, `uv cache clean`, DerivedData.
  6. Vacía `~/Library/Caches` completo, protegiendo `ms-playwright` (los navegadores de net_runner y web_gateway).
  7. Temporales del usuario (`DARWIN_USER_TEMP_DIR`) con más de 1 h.
  8. `~/Library/Logs` con más de 7 días.
  9. Papelera (si Python no tiene Acceso total al disco, se lo pide a Finder).
  10. `~/Library/Saved Application State` (las apps no restauran ventanas).
  11. `defaults write com.apple.loginwindow TALLogoutSavesState false` y `NSQuitAlwaysKeepsWindows false`.
  12. `dscacheutil -flushcache`.
  13. Lista ítems de inicio de sesión y LaunchAgents (solo informa; no borra nada tuyo).
  Al terminar vuelve a medir y la tarjeta dice "Listo para reiniciar (liberó N MB)".
- **Reiniciar ahora** (pide confirmación): `osascript … System Events restart`. Una app con cambios sin
  guardar puede detener el reinicio; la tarjeta ya te habrá avisado cuál.

Los gateways de launchd (net_runner, web_gateway, graph_gateway) no se tocan: el reinicio los cierra y
launchd los vuelve a levantar al iniciar sesión.

## Permisos de macOS (primera vez)

Los pasos 4 y 13 usan AppleScript (`System Events`). La primera vez macOS pedirá autorizar
**Automatización** para el proceso que corre la Botonera (Terminal o Python). Si lo niegas, esos dos pasos
quedan marcados con ✗ en el registro y el resto sigue igual. Si `~/Library/Caches` o la Papelera dan
"Operation not permitted", es la protección de **Acceso total al disco**; agrégale Terminal en Ajustes →
Privacidad y seguridad.

## Dónde queda cada cosa

| Qué | Dónde |
|---|---|
| Script, instalador, este archivo | `~/dev/mac_health/` |
| Última medición / historial (200 lecturas) | `~/dev/mac_health/var/estado.json`, `var/historial.jsonl` |
| Estado y registro de la mantención | `~/dev/mac_health/var/mantencion.json`, `var/mantencion.log` |
| Salida del agente launchd | `~/dev/mac_health/var/launchd.log` |
| Espejo para los Cowork (skill `mac-health`) | `~/dev/cowork-local/mac_health/estado.json`, `historial.json`, `mantencion.json` |
| Ficha de la Botonera | `~/dev/botonera/servicios/mac_health.json` |
| Agente launchd | `~/Library/LaunchAgents/local.mac-health.plist` |

## Uso directo desde Terminal

```bash
P=/opt/homebrew/opt/python@3.13/bin/python3.13
$P ~/dev/mac_health/mac_health.py medir        # una línea: fecha, semáforo, recomendación
$P ~/dev/mac_health/mac_health.py tarjeta | python3 -m json.tool
$P ~/dev/mac_health/mac_health.py preparar     # mantención en segundo plano
tail -f ~/dev/mac_health/var/mantencion.log
launchctl print gui/$(id -u)/local.mac-health | grep -E "state|last exit"
```
