# Conectar tu propia solución a la Botonera

Tres recetas, de la más simple a la más completa. En todas, el resultado es un `.json` en la carpeta de
registro (`~/dev/botonera/servicios/`); la Botonera lo toma en la siguiente actualización, sin reiniciarla.
El contrato completo está en [CONTRATO.md](CONTRATO.md). Si prefieres que tu asistente de IA lo haga por ti,
pásale [PROMPT-IA.md](PROMPT-IA.md).

## Receta 1 — Algo que escucha en un puerto (maqueta, servidor de desarrollo)

No hace falta nada: la sección **Servicios web locales** lo detecta sola. Si además quieres un botón
**Iniciar**, usa `fichas-ejemplo/maqueta-puerto.json`: la tarjeta es un one-liner de Python que prueba el
puerto, y `iniciar` abre una Terminal con tu `iniciar.command`.

```bash
cp fichas-ejemplo/maqueta-puerto.json ~/dev/botonera/servicios/mi_maqueta.json
# edita: id, nombre, puerto (aparece dos veces en tarjeta.cmd), rutas
```

## Receta 2 — Un servicio bajo launchd

`botonera/estados/comun.py` ya sabe leer launchd (`launchctl print`), arrancar (`bootstrap` + `kickstart`),
reiniciar (`kickstart -k`), detener (`bootout`) y abrir el registro en Consola. Solo tienes que decirle el
label y las rutas.

```bash
cp ~/dev/botonera/estados/ejemplo_launchd.py ~/dev/botonera/estados/mi_api.py
# edita CONFIG (id, nombre, label, plist, carpeta, log) y, si quieres, extra()
python3 ~/dev/botonera/estados/mi_api.py estado | python3 -m json.tool   # prueba
cp fichas-ejemplo/launchd-servicio.json ~/dev/botonera/servicios/mi_api.json
# edita: id, nombre, rutas (python y estados/mi_api.py)
```

`extra()` es donde agregas lo que te importa ver: última actividad del log, pedidos en espera, errores de
la última hora… `comun.py` trae ayudantes (`cola_log`, `actividad`, `archivos_hoy`, `en_espera`, `hace`).

## Receta 3 — Un proceso con CLI propia (bots, agentes, servicios de IA)

Tu programa expone subcomandos y la ficha los mapea a botones. Lo que tiene que cumplir tu CLI:

| Subcomando | Imprime | Para |
|---|---|---|
| `estado --json` | `{"corriendo": bool, "tarjeta": {semaforo, titulo, subtitulo, datos[], atencion[]}}` | la tarjeta |
| `iniciar` / `detener` | `{"ok": bool, "mensaje": "…"}` | botones |
| `pendientes --json` | `{"pendientes": [...]}` | cola de aprobaciones (opcional) |
| `ver N --json`, `aprobar N`, `rechazar N --motivo M` | JSON | aprobaciones (opcional) |

Plantilla: `fichas-ejemplo/script-propio.json`. Consejos que salieron de usarla:

- **La tarjeta debe ser barata** (< 1 s): lee un archivo de estado que tu proceso actualice (un "latido"
  JSON con `latido_epoch`), no interrogues al proceso.
- **Acciones largas en segundo plano**: la acción vuelve enseguida con `{"ok": true, "mensaje": "iniciado"}` y
  la tarjeta muestra el avance en `subtitulo` ("Mantención en curso: paso 4/13"). Si el subtítulo contiene
  "en curso", "iniciando" o "ejecutando", el punto de la tarjeta compacta parpadea.
- **`atencion[]` es para lo que requiere tu mano**: una solicitud por aprobar, una sesión expirada, una app
  que no cerró. No lo uses para información normal; para eso está `datos[]`.
- **Aprobaciones con riesgo**: si tu servicio ejecuta cosas que escribió un agente, clasifica el riesgo en
  `pendientes` (`bajo`/`medio`/`alto`) y pon en `alertas_rojas` lo que instale software, modifique el sistema
  o toque datos sensibles. La Botonera exige escribir APROBAR para riesgo alto.

## Monitores (sin proceso que iniciar o detener)

`mac_health` es el ejemplo: un agente de launchd mide cada hora y deja `estado.json`; la ficha tiene
`tipo: "monitor"` (va primero en el mosaico), su tarjeta solo lee ese archivo, y sus botones lanzan
acciones (medir ahora, preparar reinicio, reiniciar). Copia ese patrón para cualquier cosa que quieras vigilar:
batería, backups, certificados por vencer, espacio en un NAS, colas de trabajo.

## Dar acceso a tu asistente de IA (solo lectura)

La Botonera es para ti; para que un agente de IA "vea" lo mismo sin poder pulsar botones, haz que tus
servicios dejen una copia de su estado en una carpeta que el agente pueda leer (en `mac_health`, la variable
`COWORK_LOCAL` apunta a esa carpeta y el espejo solo se escribe si existe). Nunca compartas con el agente la
carpeta de registro de fichas ni `botonera/`: quien escribe fichas define qué comandos se ejecutan.
