# Instalarla con tu asistente de IA, sin saber programar

No necesitas saber Python ni usar git. Necesitas una cosa: que tu asistente de IA **pueda actuar en tu Mac**,
no solo chatear. Sirven, por ejemplo: Claude (app de escritorio con el computador enlazado, o Claude Code),
Codex CLI, Cursor o Windsurf en modo agente, Copilot CLI. Un chat de navegador sin acceso a tu computador solo
podrá dictarte los pasos.

## El prompt (cópialo tal cual)

```
Quiero instalar la Botonera (https://github.com/pashekiso/botonera) en este Mac. Es un panel local que
muestra todo lo que está corriendo en mi computador con un semáforo y botones. No sé programar: hazlo tú
y explícame solo lo que yo tenga que hacer con el mouse.

1. Descarga https://github.com/pashekiso/botonera/archive/refs/heads/main.zip y descomprímelo en
   ~/Downloads/botonera (si ya existe, reemplázalo).
2. Lee README.md para entender qué hace y no me preguntes nada que esté respondido ahí.
3. Si puedes ejecutar comandos directamente en macOS, corre:
   bash ~/Downloads/botonera/instalar.command
   Si NO puedes ejecutar comandos en macOS (por ejemplo, si tu shell corre en una máquina virtual),
   dime que abra la app Terminal (Cmd+Espacio, "Terminal") y pegue esta línea, sin cambiarla:
   curl -L https://github.com/pashekiso/botonera/archive/refs/heads/main.zip -o /tmp/botonera.zip && rm -rf ~/Downloads/botonera-main && unzip -qo /tmp/botonera.zip -d ~/Downloads && bash ~/Downloads/botonera-main/instalar.command
4. Si macOS pide instalar "herramientas de línea de comandos" o dice que el archivo "no se puede abrir
   porque es de un desarrollador no identificado", explícame cómo resolverlo (Aceptar en el primer caso;
   clic derecho → Abrir en el segundo).
5. Cuando esté instalada, dime qué voy a ver en http://127.0.0.1:8790/ y qué significa cada color.
```

## Lo que va a pasar

1. Tu asistente baja y descomprime el repo. Si no puede llegar a internet desde donde corre, te pedirá que
   descargues el zip tú mismo desde el link y lo dejes en Descargas.
2. Se instala en `~/dev/botonera` (y el monitor del Mac en `~/dev/mac_health`). Nada se instala fuera de tu
   carpeta de usuario, salvo un pequeño "agente" de macOS que mide la salud del equipo cada hora.
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
