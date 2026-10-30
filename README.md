# Botonera

*[English version](README.en.md)*

Un panel local para tu Mac que muestra, con semáforo, **todo lo que tienes corriendo** —servicios propios,
agentes de IA, maquetas, servidores de desarrollo, monitores— y te da botones para iniciarlo, detenerlo,
aprobar lo que pida aprobación o revisar su registro. Un archivo de Python con biblioteca estándar, una página
HTML y una carpeta de fichas JSON. Sin dependencias, sin cuentas, sin red: escucha solo en `127.0.0.1`.

![Mosaico](docs/captura-mosaico.png)

![Detalle](docs/captura-detalle.png)

Nació de una necesidad concreta: al trabajar con varios asistentes de IA que levantan servicios, abren maquetas
y dejan procesos corriendo en la máquina, hacía falta un solo lugar donde ver qué está vivo, qué requiere
atención y cerrarlo con un clic. Cualquier solución —hecha a mano o por tu asistente de IA— se conecta dejando
un JSON de pocas líneas.

## Qué incluye

| Carpeta | Qué es |
|---|---|
| `botonera/` | El panel: `botonera.py` (servidor), `pagina.html` (mosaico + detalle), `puertos.py` (descubre servidores web locales), `estados/comun.py` (ayudante para servicios bajo launchd) y `estados/ejemplo_launchd.py` (plantilla) |
| `mac_health/` | Monitor opcional de salud del Mac: mide cada hora memoria, swap, presión, uptime, disco y servidores locales; recomienda reiniciar y, con un botón, prepara el equipo para que el reinicio lo deje limpio ([detalle](mac_health/LEEME.md)) |
| `fichas-ejemplo/` | Tres fichas de referencia: puerto simple, servicio launchd, CLI propia con aprobaciones |
| `docs/CONTRATO.md` | El contrato de ficha y tarjeta (lo que necesita saber quien conecte algo) |
| `docs/CONECTAR.md` | Recetas para sumar tus propias soluciones |
| `docs/PROMPT-IA.md` | Prompt listo para que tu asistente de IA conecte algo, o replique el panel en tu stack |
| `docs/SIN-CODIGO.md` | Para quien no programa: prompt para que su asistente de IA la instale, y qué esperar |

## Instalar

¿No programas? Pásale [docs/SIN-CODIGO.md](docs/SIN-CODIGO.md) a tu asistente de IA.

Requisitos: macOS, Python 3.9+ (viene con las herramientas de Xcode; o `brew install python`).

```bash
git clone https://github.com/pashekiso/botonera.git   # o descarga el zip: Code → Download ZIP
cd botonera
bash instalar.command               # solo el panel
bash instalar.command --con-salud   # panel + monitor de salud del Mac
open ~/dev/botonera/iniciar_botonera.command
```

La Terminal que se abre es el servidor; déjala abierta. El navegador abre `http://127.0.0.1:8790/`.
`instalar.command` se puede repetir para actualizar: conserva `config.json` y tus fichas.

## Cómo funciona

1. La Botonera lee las fichas (`*.json` con `"esquema": "botonera-servicio/1"`) de `~/dev/botonera/servicios/`.
2. Cada ficha dice con qué comando se obtiene su **tarjeta** (semáforo, título, subtítulo, datos, avisos) y qué
   **acciones** existen (cada una, un comando). Todo se ejecuta sin shell, con tiempo máximo.
3. La página pinta un mosaico de tarjetas compactas; al hacer clic se abre el detalle con los botones.
4. Aparte de las fichas, lista por sí sola los **servidores web locales** (cualquier cosa que escuche en un puerto
   de tu usuario y responda HTTP), con título, proceso, carpeta y botón Detener.
5. Si una ficha declara una cola de **aprobaciones pendientes** (por ejemplo, un agente que pide permiso para
   ejecutar un script), aparece arriba, con el riesgo en rojo cuando corresponde.

## Conectar tu solución

Lo mínimo es un JSON así en `~/dev/botonera/servicios/`:

```json
{
  "esquema": "botonera-servicio/1",
  "id": "mi_servicio",
  "nombre": "Mi servicio",
  "tipo": "servicio",
  "tarjeta": {"cmd": ["/usr/bin/python3", "/ruta/estado.py"], "cada_segundos": 10},
  "acciones": {
    "iniciar": {"cmd": ["/ruta/iniciar.sh"]},
    "detener": {"cmd": ["/ruta/detener.sh"], "confirmar": true}
  }
}
```

y que `/ruta/estado.py` imprima `{"tarjeta": {"semaforo": "verde", "titulo": "Mi servicio", "subtitulo": "Corriendo", "datos": [], "atencion": []}}`.
Recetas completas en [docs/CONECTAR.md](docs/CONECTAR.md); contrato en [docs/CONTRATO.md](docs/CONTRATO.md).
Si trabajas con un asistente de IA, [docs/PROMPT-IA.md](docs/PROMPT-IA.md) le explica todo.

## Seguridad

- Solo `127.0.0.1`; rechaza peticiones con otro `Host`.
- Token por arranque embebido en la página: una web abierta en otra pestaña no puede pulsar tus botones.
- Ejecuta solo los comandos declarados en las fichas, sin shell, con validación de los valores que reemplaza.
- La carpeta de fichas define qué se ejecuta: **no la compartas** con agentes de IA ni con otros usuarios.
  Para que un agente vea el estado, haz que tus servicios dejen una copia de solo lectura en otra carpeta
  (así lo hace `mac_health`).

## Limitaciones conocidas

- macOS solamente (`launchctl`, `lsof`, `osascript`). Portarlo a Linux pide reemplazar `comun.py` (systemd)
  y los pasos de mantención de `mac_health`.
- La mantención de `mac_health` que cierra apps usa AppleScript: la primera vez macOS pide permiso de
  Automatización; vaciar `~/Library/Caches` y la Papelera puede pedir Acceso total al disco para Terminal.
- No hay autenticación más allá del token local: está pensada para una sola persona en su propio equipo.

## Licencia

MIT. Hecha por [Gerardo Oyarce](https://github.com/pashekiso) con ayuda de Claude.
