# Instrucciones para el asistente de IA: instalar la Botonera

Este archivo está escrito para ti, el asistente. La persona que te lo pasó probablemente no programa y quiere
intervenir lo menos posible. Tu trabajo: instalar la Botonera en su Mac, o darle el camino más corto posible,
y al final explicarle en lenguaje simple qué tiene y cómo se usa. No le preguntes nada que esté aquí.

## Qué es

Un panel local en `http://127.0.0.1:8790/` que muestra con semáforo todo lo que corre en el Mac (servicios,
agentes de IA, maquetas, servidores de desarrollo) y un monitor de salud (OSHealth) que recomienda cuándo
reiniciar y limpia el equipo antes. Solo macOS. Python 3.9+ (sin dependencias). Se instala en `~/dev/botonera`
y `~/dev/mac_health`, más dos agentes de usuario en `~/Library/LaunchAgents/` (`local.botonera`,
`local.mac-health`). Nada fuera de la carpeta del usuario. Repo: https://github.com/pashekiso/botonera

## Si ya existen `~/dev/botonera` o `~/dev/mac_health`

Es una reinstalación o actualización: el instalador copia los archivos del programa encima y **conserva**
`config.json` y todo lo que haya en `servicios/` (las fichas propias de la persona), sus registros en `var/` y
sus mediciones. Lo único que reemplaza es `LEEME.md`. No hace falta respaldar nada ni advertir de pérdidas; el
servicio se recarga un par de segundos y la página se reconecta sola.

## Paso 0 — ¿Mac o Windows?

Si la persona no lo dijo, mira el shell: `uname -s` responde `Darwin` en Mac; en Windows `uname` no existe y
`$env:OS` (PowerShell) o `echo %OS%` (cmd) responde `Windows_NT`. Si no tienes shell, pregúntale "¿tu
computador es Mac o Windows?" y nada más. **Windows está en beta**: dilo en una frase y sigue.

## Paso 1 — Averigua qué puedes hacer tú

Ejecuta `uname -s` y `sw_vers` en el shell que tengas.

- Si responde `Darwin` y `sw_vers` funciona → tienes **shell en macOS**: sigue el camino A.
- Si responde `Linux`, o no tienes shell, o el shell corre en una máquina virtual (típico de asistentes de
  escritorio que enlazan el computador) → **no puedes instalar tú**: sigue el camino B. No pierdas tiempo
  intentando `launchctl` u `osascript` desde ahí: no existen.

## Mac — Camino A (shell en macOS)

```bash
curl -L https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -o /tmp/botonera.zip \
 && rm -rf ~/Downloads/botonera-main && unzip -qo /tmp/botonera.zip -d ~/Downloads \
 && bash ~/Downloads/botonera-main/instalar.command
```

- Si `python3` no existe o dispara el diálogo de "herramientas de línea de comandos": dile a la persona que
  pulse **Instalar** en ese diálogo, espera a que termine (varios minutos) y repite el comando.
- Si tu entorno te pide permiso para escribir en `~/dev` o en `~/Library/LaunchAgents`, pídeselo a la persona
  con una frase simple ("necesito permiso para instalar el panel y su inicio automático"). Si lo niega o el
  entorno lo bloquea, el panel puede quedar instalado sin servicio: dile que abra `~/dev/botonera/iniciar_botonera.command`
  con doble clic cada vez que quiera usarlo, o que te vuelva a pedir la instalación con el permiso concedido.
- Si el instalador termina con "servicio local.botonera corriendo", abre `http://127.0.0.1:8790/` (el
  instalador ya lo intenta con `open`). Comprueba con `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8790/`
  que responde 200.
- Si algo falla, lee `~/dev/botonera/var/botonera.log` y `~/dev/mac_health/var/launchd.log` antes de
  preguntar nada.

## Windows — Camino A (shell en Windows: PowerShell o cmd en el equipo de la persona)

```powershell
Invoke-WebRequest https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -OutFile "$env:TEMP\botonera.zip"
Expand-Archive "$env:TEMP\botonera.zip" -DestinationPath "$env:USERPROFILE\Downloads" -Force
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\botonera-main\instalar.ps1"
```

- Si no hay Python, el instalador lo instala con `winget` (puede abrir un diálogo de control de cuentas: que
  pulse **Sí**). Si `winget` no existe, dile que instale Python desde python.org marcando "Add python.exe to
  PATH" y repite el instalador.
- Comprueba: `Invoke-WebRequest http://127.0.0.1:8790/ -UseBasicParsing | Select-Object StatusCode` → 200.
- Registros: `%USERPROFILE%\dev\botonera\var\botonera.log` y `%USERPROFILE%\dev\win_health\var\`.

## Windows — Camino B (no puedes ejecutar en su equipo)

1. "Pulsa la tecla Windows, escribe **PowerShell**, pulsa Enter."
2. "Copia esta línea completa, pégala en la ventana azul y pulsa Enter:"

   ```
   Invoke-WebRequest https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -OutFile "$env:TEMP\botonera.zip"; Expand-Archive "$env:TEMP\botonera.zip" -DestinationPath "$env:USERPROFILE\Downloads" -Force; powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\botonera-main\instalar.ps1"
   ```

3. "Si aparece una ventana pidiendo permiso para instalar Python, pulsa **Sí** y espera."
4. "Cuando termine, se abre tu navegador solo. Si no, abre `http://127.0.0.1:8790/`."

En Windows, la mantención de OSHealth vacía la **Papelera de reciclaje** y apaga Docker Desktop/WSL; el aviso
previo lo dice. *Reiniciar ahora* usa `shutdown /r` sin forzar.

## Camino B — No puedes instalar tú (Mac)

Dale a la persona exactamente esto, en este orden, sin agregar alternativas:

1. "Abre la app **Terminal**: pulsa `Cmd + Espacio`, escribe `Terminal`, pulsa Enter."
2. "Copia esta línea completa, pégala en la ventana negra y pulsa Enter:"

   ```
   curl -L https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -o /tmp/botonera.zip && rm -rf ~/Downloads/botonera-main && unzip -qo /tmp/botonera.zip -d ~/Downloads && bash ~/Downloads/botonera-main/instalar.command
   ```

3. "Si aparece un aviso pidiendo instalar *herramientas de línea de comandos* (o *command line tools*),
   pulsa **Instalar**, espera a que termine y vuelve a pegar la misma línea."
4. "Cuando termine, se abre tu navegador solo. Si no, abre esta dirección: `http://127.0.0.1:8790/`."

Pídele que te pegue lo que diga la Terminal si algo sale mal, y resuélvelo con el registro que te muestre.

## Lo que debes explicarle al final (en tus palabras, corto)

- El panel vive en `http://127.0.0.1:8790/`; solo se ve desde su propio Mac; arranca solo al iniciar sesión;
  no queda ninguna ventana abierta.
- Cada tarjeta tiene un punto: **verde** corre bien · **amarillo** pide atención · **rojo** tiene problemas ·
  **gris** detenido. Clic en una tarjeta → detalle y botones.
- La tarjeta **OSHealth** le dice si conviene reiniciar. *Preparar reinicio* cierra apps y procesos, **vacía la
  Papelera** y borra cachés (algunas apps tardan más en abrir la primera vez); muestra un aviso antes y una barra
  de avance; *Reiniciar ahora* se habilita solo cuando esa preparación termina. La primera vez macOS pedirá
  permiso de **Automatización**: que acepte si quiere que pueda cerrar apps por él.
- "Servicios web locales" lista lo que sus herramientas dejaron abierto (maquetas, servidores); con *Detener*
  los cierra.
- Para quitarla: que te lo pida y ejecutas `python3 ~/dev/botonera/botonera.py servicio desinstalar`,
  `python3 ~/dev/mac_health/mac_health.py desinstalar` y borras `~/dev/botonera` y `~/dev/mac_health`.

## Si te piden conectar otra cosa al panel

Lee `docs/CONTRATO.md` y `docs/CONECTAR.md` del repo: cualquier servicio entra dejando un JSON en
`~/dev/botonera/servicios/`. No modifiques `botonera.py`, `pagina.html` ni `puertos.py`.
