# Instalarla con tu asistente de IA, sin saber programar

(Mac, y Windows en beta: el mismo prompt sirve; en Windows el panel arranca desde la carpeta Inicio y OSHealth como tarea programada.)

No necesitas saber Python ni usar git. Necesitas una cosa: que tu asistente de IA **pueda actuar en tu computador**,
no solo chatear. Sirven, por ejemplo: Claude (app de escritorio con el computador enlazado, o Claude Code),
Codex CLI, Cursor o Windsurf en modo agente, Copilot CLI. Un chat de navegador sin acceso a tu computador solo
podrá dictarte los pasos.

## El prompt (cópialo tal cual)

```
Quiero instalar una webapp local en este computador con la menor intervención posible de mi parte. Sigue las
instrucciones de https://github.com/pashekiso/botonera/blob/main/docs/INSTALAR-IA.md y, si no puedes
instalarla tú, dame el paso a paso más sencillo según lo que tenga mi máquina.
```

Eso es todo. Las instrucciones largas están en ese archivo, escritas para la IA: cómo saber si tu computador es Mac
o Windows y si puede instalar por ti, qué hacer si no, los avisos típicos de cada sistema y qué contarte al final.
Si tu asistente no te pregunta ni dice qué sistema tienes, dile "es Windows" (o "es Mac") y sigue.
En Windows, lo normal es que te pida permiso para dejar archivos en Descargas y luego te diga que hagas doble
clic en `instalar.cmd`; en Mac, que pegues una línea en Terminal.

## Lo que va a pasar

1. Tu asistente baja y descomprime el repo. Si no puede llegar a internet desde donde corre, te pedirá que
   descargues el zip tú mismo desde el link y lo dejes en Descargas.
2. Se instala dentro de tu carpeta de usuario, en `dev/botonera` y `dev/mac_health` (Mac) o `dev\win_health`
   (Windows). Lo único fuera de ahí es el arranque automático: en Mac, dos pequeños "agentes" en
   `~/Library/LaunchAgents` (uno mantiene el panel, el otro mide la salud cada hora); en Windows, un lanzador
   `Botonera.vbs` en tu carpeta Inicio y una tarea programada `OSHealth`. Si tu asistente te pide permiso para
   escribir en esas carpetas, acéptalo; si no, el panel queda instalado pero no arranca solo: ábrelo con doble
   clic en `iniciar_botonera.command` (Mac) o `iniciar_botonera.cmd` (Windows), dentro de `dev/botonera`.
3. Al terminar, el panel ya está corriendo: no queda ninguna ventana abierta y vuelve a arrancar solo cada vez
   que inicias sesión. Se abre tu navegador en `http://127.0.0.1:8790/`; esa dirección solo funciona desde tu
   propio computador. Si algún día no carga, doble clic en el `iniciar_botonera` de arriba.
4. Verás tarjetas con un punto de color: verde corre bien, amarillo pide tu atención, rojo tiene problemas,
   gris está detenido. Clic en una tarjeta → detalle y botones.
5. La tarjeta **OSHealth** te dice si conviene reiniciar y tiene el botón *Preparar reinicio*, que cierra lo
   que quedó abierto, vacía la Papelera y limpia cachés antes de reiniciar (te lo avisa antes). En Mac, la
   primera vez te pedirá permiso de "Automatización"; acepta si quieres que pueda cerrar apps por ti.

## Si algo no sale

- Mac, "no se puede abrir porque es de un desarrollador no identificado": clic derecho sobre el archivo → Abrir.
- Mac, un diálogo pide instalar las herramientas de línea de comandos: Aceptar; tarda unos minutos y es de Apple.
- Windows, una ventana pide permiso para instalar Python: Sí; si no aparece `winget`, instala Python desde
  python.org marcando "Add python.exe to PATH" y repite.
- El panel dice "sin conexión con la botonera": el servicio se detuvo; doble clic en `iniciar_botonera.command`
  (Mac) o `iniciar_botonera.cmd` (Windows), dentro de `dev/botonera`.
- Cualquier otra cosa: pega el mensaje de error a tu asistente junto con el link del repo.

## Para desinstalar

Dile a tu asistente: "Desinstala la Botonera siguiendo https://github.com/pashekiso/botonera/blob/main/docs/INSTALAR-IA.md".
Son dos comandos (quitan el arranque automático y la tarea horaria) y borrar dos carpetas; no deja nada más en el sistema.
