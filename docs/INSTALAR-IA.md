# Instrucciones para el asistente de IA: instalar la Botonera

Este archivo está escrito para ti, el asistente. La persona que te lo pasó probablemente no programa y quiere
intervenir lo menos posible. Tu trabajo: instalar la Botonera en su computador (Mac o Windows), o darle el
camino más corto posible, y al final explicarle en lenguaje simple qué tiene y cómo se usa. No le preguntes
nada que esté aquí.

## Qué es

Un panel local en `http://127.0.0.1:8790/` que muestra con semáforo todo lo que corre en el computador
(servicios, agentes de IA, maquetas, servidores de desarrollo) y un monitor de salud (OSHealth) que
recomienda cuándo reiniciar y limpia el equipo antes. Funciona en **macOS** y en **Windows 10/11** (beta).
Python 3.9+ sin dependencias (en Windows el instalador lo instala si falta). Nada fuera de la carpeta del
usuario; no pide administrador. Repo: https://github.com/pashekiso/botonera

## Paso 0 (obligatorio) — ¿El computador de la persona es Mac o Windows?

Decide esto ANTES de cualquier otra cosa, y dilo en tu primera frase ("Tu computador es Windows, así que…").

1. Si tienes una herramienta que describe el dispositivo enlazado (p. ej. `get_device_info` en la app de
   Claude: `platform` = `darwin` → Mac, `win32` → Windows), úsala: es la fuente más fiable.
2. Si tienes un shell **en el computador de la persona**: `uname -s` → `Darwin` es Mac; si `uname` no existe
   y `echo %OS%` o `$env:OS` responde `Windows_NT`, es Windows.
3. **Un shell Linux (en la nube o en una máquina virtual) no dice nada del computador de la persona.** Si es
   lo único que tienes y no hay herramienta de dispositivo, pregúntale "¿Tu computador es Mac o Windows?" y
   espera la respuesta. No asumas Mac.

Luego decide, en este orden: si puedes ejecutar comandos **en ese computador** (no en tu nube/VM), camino A;
si no, pero tienes herramientas de archivos sobre sus carpetas y control de pantalla, camino A2; si solo tienes
herramientas de archivos, camino A3 (Windows) o B (Mac); si no tienes nada de eso, camino B. En los caminos
A3 y B dale exactamente los pasos indicados, en orden, sin agregar alternativas.

## Si ya existen `~/dev/botonera` (Mac) o `%USERPROFILE%\dev\botonera` (Windows)

Es una reinstalación o actualización: el instalador copia los archivos del programa encima y **conserva**
`config.json`, las fichas en `servicios/`, los registros en `var/` y las mediciones. Solo reemplaza `LEEME.md`.
No hace falta respaldar nada ni advertir de pérdidas; el panel se recarga un par de segundos.

---

# macOS

## Mac — Camino A (tienes shell en el Mac de la persona)

```bash
curl -L https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -o /tmp/botonera.zip \
 && rm -rf ~/Downloads/botonera-main && unzip -qo /tmp/botonera.zip -d ~/Downloads \
 && bash ~/Downloads/botonera-main/instalar.command
```

- Si `python3` no existe o dispara el diálogo de "herramientas de línea de comandos": que pulse **Instalar**,
  espera a que termine (varios minutos) y repite el comando.
- Si tu entorno pide permiso para escribir en `~/dev` o `~/Library/LaunchAgents`, pídeselo con una frase simple
  ("necesito permiso para instalar el panel y su inicio automático"). Si lo niega o se bloquea, el panel puede
  quedar sin servicio: que lo abra con doble clic en `~/dev/botonera/iniciar_botonera.command`.
- Comprueba: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8790/` → 200.
- Registros: `~/dev/botonera/var/botonera.log`, `~/dev/mac_health/var/launchd.log`.

## Mac — Camino A2 (sin shell en el Mac, pero con herramientas de archivos y control de pantalla)

Como en Windows (ver más abajo), puedes escribir `botonera-main` en `~/Downloads` con las herramientas de
archivos y luego, con control de pantalla, abrir Terminal desde Launchpad y arrastrar `instalar.command` a la
ventana, o escribir en ella la línea del camino B. Si el control de pantalla no permite escribir en Terminal
(suele ser así), usa el camino B.

## Mac — Camino B (no puedes ejecutar en el Mac)

1. "Abre la app **Terminal**: pulsa `Cmd + Espacio`, escribe `Terminal`, pulsa Enter."
2. "Copia esta línea completa, pégala en la ventana y pulsa Enter:"

   ```
   curl -L https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -o /tmp/botonera.zip && rm -rf ~/Downloads/botonera-main && unzip -qo /tmp/botonera.zip -d ~/Downloads && bash ~/Downloads/botonera-main/instalar.command
   ```

3. "Si aparece un aviso pidiendo instalar *herramientas de línea de comandos*, pulsa **Instalar**, espera a que
   termine y vuelve a pegar la misma línea."
4. "Cuando termine, se abre tu navegador solo. Si no, abre `http://127.0.0.1:8790/`."

Qué queda en Mac: `~/dev/botonera`, `~/dev/mac_health`, dos agentes de usuario en `~/Library/LaunchAgents/`
(`local.botonera` mantiene el panel; `local.mac-health` mide cada hora). La mantención de OSHealth vacía la
**Papelera** y borra cachés; la primera vez macOS pide permiso de **Automatización** para cerrar apps.

---

# Windows (beta)

## Windows — Camino A (tienes PowerShell o cmd en el Windows de la persona)

```powershell
Invoke-WebRequest https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -OutFile "$env:TEMP\botonera.zip"
Expand-Archive "$env:TEMP\botonera.zip" -DestinationPath "$env:USERPROFILE\Downloads" -Force
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\botonera-main\instalar.ps1"
```

- Si no hay Python, el instalador lo instala con `winget` (puede abrir un diálogo de control de cuentas: que
  pulse **Sí**). Si `winget` no existe, que instale Python desde python.org marcando "Add python.exe to PATH" y
  repite el instalador.
- Comprueba: `Invoke-WebRequest http://127.0.0.1:8790/ -UseBasicParsing | Select-Object StatusCode` → 200.
- Registros: `%USERPROFILE%\dev\botonera\var\botonera.log`, `%USERPROFILE%\dev\win_health\var\`.

## Windows — Camino A2 (no tienes shell en el Windows, pero sí herramientas de archivos y control de pantalla)

Es el caso de la app de Claude con el computador enlazado. Puedes instalar sin que la persona escriba nada:

1. En tu shell (Linux en la nube) descarga y descomprime el repo:
   `curl -L https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -o /tmp/b.zip && unzip -qo /tmp/b.zip -d /tmp`.
2. Pide acceso a la carpeta **Downloads** (Descargas) de la persona y escribe ahí la carpeta completa
   `botonera-main` con las herramientas de archivos (todos los archivos, conservando la estructura). Los
   archivos escritos así no llevan la marca "descargado de internet", así que SmartScreen no interviene.
3. Con control de pantalla: abre el Explorador en `Downloads\botonera-main` y haz **doble clic en
   `instalar.cmd`**. No hace falta escribir en ninguna terminal: el `.cmd` abre su propia ventana, instala, abre
   el navegador y se queda esperando una tecla para que puedas leer el resultado.
4. Toma una captura de esa ventana: debe decir "Botonera corriendo en http://127.0.0.1:8790/". Si en vez de eso
   pide instalar Python o permiso de control de cuentas, pulsa **Sí** (o pídeselo a la persona) y espera.
5. Si el control de pantalla no te deja hacer el doble clic, cae al camino B.

## Windows — Camino A3 (sin shell ni control de pantalla, pero con herramientas de archivos)

Es el camino preferido cuando no puedes ejecutar en el equipo: la persona solo hace un doble clic.

1. En tu shell descarga y descomprime el repo (`curl -L https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -o /tmp/b.zip && unzip -qo /tmp/b.zip -d /tmp`).
2. Pide acceso a la carpeta **Downloads** (Descargas) con una frase simple ("necesito permiso para dejar los
   archivos del panel en tu carpeta Descargas") y escribe ahí la carpeta completa `botonera-main`, con todos
   sus archivos y subcarpetas (`botonera\`, `botonera\estados\`, `win_health\`, `docs\`, `fichas-ejemplo\`,
   `instalar.cmd`, `instalar.ps1`, `README.md`). Sin la marca "descargado de internet", SmartScreen no interviene.
3. Dile a la persona, exactamente: "Abre la carpeta **Descargas**, entra a **botonera-main** y haz **doble clic en
   `instalar.cmd`**. Se abre una ventana negra que instala todo; cuando diga *Botonera corriendo* y *Listo*, pulsa
   cualquier tecla para cerrarla. Si aparece una ventana pidiendo permiso para instalar Python, pulsa **Sí**."
4. Verifica con las herramientas de archivos que existan `dev\botonera\var\botonera.pid` y
   `dev\botonera\var\botonera.log` en su carpeta de usuario (pide acceso a `dev` si hace falta), y explícale
   el resultado. Si no aparecen, pídele que te diga qué mostró la ventana negra.

## Windows — Camino B (no puedes ejecutar en el Windows ni escribir archivos)

1. "Pulsa la tecla **Windows**, escribe **PowerShell**, pulsa Enter."
2. "Copia esta línea completa, pégala en la ventana azul y pulsa Enter:"

   ```
   Invoke-WebRequest https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -OutFile "$env:TEMP\botonera.zip"; Expand-Archive "$env:TEMP\botonera.zip" -DestinationPath "$env:USERPROFILE\Downloads" -Force; powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\Downloads\botonera-main\instalar.ps1"
   ```

3. "Si aparece una ventana pidiendo permiso para instalar Python, pulsa **Sí** y espera."
4. "Cuando termine, se abre tu navegador solo. Si no, abre `http://127.0.0.1:8790/`."

Qué queda en Windows: `%USERPROFILE%\dev\botonera`, `%USERPROFILE%\dev\win_health`, un lanzador
`Botonera.vbs` en la carpeta Inicio del usuario (arranca el panel sin ventana al iniciar sesión) y una tarea
programada `OSHealth` (cada hora). No pide administrador. La mantención de OSHealth vacía la **Papelera de
reciclaje**, apaga Docker Desktop/WSL y borra temporales; *Reiniciar ahora* usa `shutdown /r` sin forzar.

---

## Lo que debes explicarle al final (en tus palabras, corto, sin mezclar Mac y Windows)

- El panel vive en `http://127.0.0.1:8790/`; solo se ve desde su propio computador; arranca solo al iniciar
  sesión; no queda ninguna ventana abierta.
- Cada tarjeta tiene un punto: **verde** corre bien · **amarillo** pide atención · **rojo** tiene problemas ·
  **gris** detenido. Clic en una tarjeta → detalle y botones.
- La tarjeta **OSHealth** le dice si conviene reiniciar. *Preparar reinicio* cierra apps y procesos, vacía la
  Papelera y borra cachés (algunas apps tardan más en abrir la primera vez); muestra un aviso antes y una barra
  de avance; *Reiniciar ahora* se habilita solo cuando esa preparación termina.
- "Servicios web locales" lista lo que sus herramientas dejaron abierto (maquetas, servidores); con *Detener*
  los cierra.
- Para quitarla: que te lo pida. Mac: `python3 ~/dev/botonera/botonera.py servicio desinstalar`,
  `python3 ~/dev/mac_health/mac_health.py desinstalar`, borrar `~/dev/botonera` y `~/dev/mac_health`.
  Windows: `python %USERPROFILE%\dev\botonera\botonera.py servicio desinstalar`,
  `python %USERPROFILE%\dev\win_health\win_health.py desinstalar`, borrar esas dos carpetas.

## Si te piden conectar otra cosa al panel

Lee `docs/CONTRATO.md` y `docs/CONECTAR.md` del repo: cualquier servicio entra dejando un JSON en la carpeta
`servicios/`. No modifiques `botonera.py`, `pagina.html` ni `puertos.py`.
