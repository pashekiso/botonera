# Instalarla con tu asistente de IA, sin saber programar

(Mac, y Windows en beta: el mismo prompt sirve; en Windows el panel y OSHealth corren como tareas programadas.)

No necesitas saber Python ni usar git. Necesitas una cosa: que tu asistente de IA **pueda actuar en tu Mac**,
no solo chatear. Sirven, por ejemplo: Claude (app de escritorio con el computador enlazado, o Claude Code),
Codex CLI, Cursor o Windsurf en modo agente, Copilot CLI. Un chat de navegador sin acceso a tu computador solo
podrá dictarte los pasos.

## El prompt (cópialo tal cual)

```
Quiero instalar una webapp local en este computador con la menor intervención posible de mi parte. Sigue las
instrucciones de https://github.com/pashekiso/botonera/blob/main/docs/INSTALAR-IA.md y, si no puedes
instalarla tú, dame el paso a paso más sencillo según lo que tenga mi máquina.
```

Eso es todo. Las instrucciones largas están en ese archivo, escritas para la IA: cómo saber si puede instalar
por ti, qué hacer si no, los avisos típicos de macOS y qué contarte al final.

## Lo que va a pasar

1. Tu asistente baja y descomprime el repo. Si no puede llegar a internet desde donde corre, te pedirá que
   descargues el zip tú mismo desde el link y lo dejes en Descargas.
2. Se instala en `~/dev/botonera` (y el monitor del Mac en `~/dev/mac_health`). Nada se instala fuera de tu
   carpeta de usuario, salvo dos pequeños "agentes" de macOS en `~/Library/LaunchAgents` (uno mantiene el panel
   encendido, el otro mide la salud del equipo cada hora). Si tu asistente te pide permiso para escribir en esas
   carpetas, acéptalo; si no se lo das, el panel queda instalado pero no arranca solo: ábrelo con doble clic en
   `~/dev/botonera/iniciar_botonera.command`.
3. Al terminar, el panel ya está corriendo como un servicio de tu usuario: no queda ninguna ventana abierta y
   vuelve a arrancar solo cada vez que inicias sesión. Se abre tu navegador en `http://127.0.0.1:8790/`; esa
   dirección solo funciona desde tu propio Mac. Si algún día no carga, doble clic en
   `~/dev/botonera/iniciar_botonera.command`.
4. Verás tarjetas con un punto de color: verde corre bien, amarillo pide tu atención, rojo tiene problemas,
   gris está detenido. Clic en una tarjeta → detalle y botones.
5. La tarjeta **OSHealth** te dice si conviene reiniciar y tiene el botón *Preparar reinicio*, que cierra lo
   que quedó abierto y limpia cachés antes de reiniciar. La primera vez macOS te pedirá permiso de
   "Automatización"; acepta si quieres que pueda cerrar apps por ti.

## Si algo no sale

- "No se puede abrir porque es de un desarrollador no identificado": clic derecho sobre el archivo → Abrir.
- Un diálogo pide instalar las herramientas de línea de comandos: Aceptar; tarda unos minutos y es de Apple.
- El panel dice "sin conexión con la botonera": el servicio se detuvo; doble clic en
  `~/dev/botonera/iniciar_botonera.command`.
- Cualquier otra cosa: pega el mensaje de error a tu asistente junto con el link del repo.

## Para desinstalar

Dile a tu asistente: "Desinstala la Botonera: ejecuta `python3 ~/dev/botonera/botonera.py servicio desinstalar`
y `python3 ~/dev/mac_health/mac_health.py desinstalar`, y borra las carpetas `~/dev/botonera` y
`~/dev/mac_health`". No deja nada más en el sistema.
