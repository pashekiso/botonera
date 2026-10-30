# win_health — OSHealth para Windows (beta)

Equivalente de `mac_health` para Windows. Misma tarjeta en la Botonera (OSHealth), mismos botones, mismo
contrato; cambian las fuentes de datos y los pasos de limpieza. **Beta**: escrito sin un Windows a mano para
probarlo; si algo falla, el registro está en `%USERPROFILE%\dev\win_health\var\` y los umbrales en `UMBRAL`.

## Instalar

Lo hace `instalar.cmd` del repo (salvo `--sin-salud`). A mano: `python win_health.py instalar`. Crea la tarea
programada **OSHealth** (cada hora, con tu sesión iniciada) y la ficha `botonera\servicios\mac_health.json`
(mismo nombre de ficha que en Mac para que la skill `mac-health` lea el mismo espejo).

## Qué mide y cómo decide

| Señal | Fuente | Amarillo | Rojo |
|---|---|---|---|
| Archivo de paginación en uso | `Win32_PageFileUsage` | > 1.5 GB | > 4 GB |
| Tiempo encendido | `Win32_OperatingSystem.LastBootUpTime` | > 3 días | > 7 días |
| Memoria libre | `FreePhysicalMemory / TotalVisibleMemorySize` | < 12 % | < 5 % |
| Páginas escritas a disco | `PerfOS_Memory.PagesOutputPersec` | > 50/s ahora | > 50/s en 3 lecturas seguidas |
| Disco libre (unidad del perfil) | `shutil.disk_usage` | < 25 GB | < 10 GB |
| CPU | `Win32_Processor.LoadPercentage` | > 85 % (tras 10 min de encendido) | — |
| Servidores locales de maquetas | `netstat -ano` + `Win32_Process` | > 5 | — |
| Temporales y cachés de usuario | `%TEMP%`, `%LOCALAPPDATA%\Temp`, pip, npm, CrashDumps, WER, D3DSCache, DXCache | > 10 GB | — |

Con **inicio rápido** de Windows, "apagar" no reinicia el contador de encendido (es una hibernación del
núcleo); solo *Reiniciar* lo hace. Por eso el uptime puede sorprender.

## Pasos de "Preparar reinicio"

1. Cierra Docker Desktop y apaga WSL (`wsl --shutdown`) si están corriendo.
2. Cierra los servidores que escuchan en puertos locales, salvo la Botonera, Windows, `Program Files`,
   apps instaladas en `AppData\Local\Programs`, Docker/WSL y navegadores. Un `node.exe` o `python.exe`
   instalado en `Program Files` pero ejecutando un script bajo tu perfil (`~\dev\…`) sí se cierra.
3. Cierra procesos de pruebas: uvicorn, http.server, vite, streamlit, Playwright/Chrome headless, ngrok…
4. Pide cerrar (`CloseMainWindow`) a las apps con ventana, salvo Explorador, Terminal, Claude y navegadores. Las
   que no cierren (documentos sin guardar) se listan en la tarjeta.
5. `npm cache clean --force`, `pip cache purge`, `uv cache clean`.
6. Vacía `%TEMP%` (más de 1 h) y las cachés de usuario listadas arriba. Los archivos en uso no se tocan.
7. Vacía la Papelera de reciclaje (`Clear-RecycleBin -Force`).
8. Desactiva "reabrir apps al iniciar sesión" (`Winlogon\RestartApps = 0`).
9. `ipconfig /flushdns`.
10. Lista los programas de inicio (`Win32_StartupCommand`); solo informa.

*Reiniciar ahora* ejecuta `shutdown /r /t 0` sin `/f`: una app con cambios sin guardar detiene el reinicio y
Windows te lo muestra. Nada requiere permisos de administrador.

## Dónde queda cada cosa

| Qué | Dónde |
|---|---|
| Script y este archivo | `%USERPROFILE%\dev\win_health\` |
| Última medición / historial | `…\win_health\var\estado.json`, `var\historial.jsonl` |
| Estado y registro de la mantención | `…\win_health\var\mantencion.json`, `var\mantencion.log` |
| Ficha de la Botonera | `%USERPROFILE%\dev\botonera\servicios\mac_health.json` |
| Tarea programada | `OSHealth` (Programador de tareas, cada hora) |
