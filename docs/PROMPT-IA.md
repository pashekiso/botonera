# Prompt para tu asistente de IA

Copia lo que sigue en Claude, ChatGPT, Gemini, Copilot o el asistente que uses (idealmente uno con acceso a tu
terminal, como Claude Code, Codex CLI, Cursor o Aider). Reemplaza lo que va entre `<>`.

---

Tengo instalada la **Botonera** (https://github.com/pashekiso/botonera): un panel local en
`http://127.0.0.1:8790/` que muestra con semáforo todo lo que corre en mi Mac y me da botones para controlarlo.
Está en `~/dev/botonera/` y lee fichas JSON desde `~/dev/botonera/servicios/`. El contrato de las fichas está en
`docs/CONTRATO.md` del repo (léelo completo antes de escribir nada) y hay tres ejemplos en `fichas-ejemplo/`.

Quiero sumar a la Botonera esto: **<describe tu servicio: qué es, cómo se inicia, dónde está, cómo sé que está
vivo, dónde escribe su log>**.

Haz lo siguiente:

1. Decide qué receta aplica (`docs/CONECTAR.md`): puerto simple, servicio bajo launchd, o CLI propia. Si es
   launchd, parte de `~/dev/botonera/estados/ejemplo_launchd.py`; si es una CLI propia, agrégale los
   subcomandos `estado --json`, `iniciar`, `detener` si no los tiene.
2. Escribe el script de estado (si hace falta) y la ficha `~/dev/botonera/servicios/<id>.json` con **rutas
   absolutas** de mi equipo (mi usuario es `<usuario>`, mi Python está en `<ruta de python3>`).
3. La tarjeta debe responder en menos de 1 segundo y devolver `semaforo`, `titulo`, `subtitulo`, `datos[]` y
   `atencion[]`. Verde si corre, amarillo si requiere mi atención, rojo si tiene problemas, gris si está detenido.
4. Pruébala antes de darla por lista: ejecuta el `tarjeta.cmd` a mano y muéstrame el JSON; luego ejecuta cada
   acción y muéstrame su salida.
5. No modifiques `botonera.py`, `pagina.html` ni `puertos.py`: todo se resuelve con fichas y scripts de estado.
6. Cualquier acción que tarde más de 60 s debe lanzarse en segundo plano y reflejar su avance en el subtítulo
   de la tarjeta.

Al terminar, dime qué archivos creaste, en qué carpeta, y qué veré en la Botonera.

---

## Prompt para replicar la solución completa con otro proveedor

Si no quieres instalar este repo sino que tu asistente construya algo equivalente en tu propio stack:

> Construye un panel local (solo `127.0.0.1`, un token por arranque, sin dependencias fuera de la biblioteca
> estándar) que lea "fichas" JSON de una carpeta, ejecute el comando de estado de cada una cada N segundos sin
> shell, y muestre un mosaico de tarjetas compactas con semáforo (verde/amarillo/rojo/gris), nombre y una línea
> de subtítulo; al hacer clic se abre un panel lateral con los datos, los avisos y los botones declarados en la
> ficha. Además, lista por sí solo todos los servidores web que escuchan en puertos locales de mi usuario, con
> título de página, proceso y botón para detenerlos. El contrato de ficha y de tarjeta debe ser el de
> https://github.com/pashekiso/botonera/blob/main/docs/CONTRATO.md para que las fichas sean intercambiables.
