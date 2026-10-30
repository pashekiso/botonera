# Contrato de una ficha (`botonera-servicio/1`)

La Botonera no sabe nada de tus servicios. Lo único que hace es:

1. Leer todos los `*.json` de la carpeta de registro (`config.json` → `registro`, por defecto `~/dev/botonera/servicios/`)
   que tengan `"esquema": "botonera-servicio/1"` y un `id`.
2. Ejecutar cada `tarjeta.cmd` cada `cada_segundos` y pintar el JSON que devuelve.
3. Cuando pulsas un botón, ejecutar el `cmd` de esa acción y mostrar su `mensaje`.

Todo se ejecuta **sin shell** (lista de argumentos), con tope de 15 s para la tarjeta y 90 s para una acción.
Si una acción tarda más, lánzala en segundo plano y refleja el avance en la tarjeta (así lo hace `mac_health`).

## La ficha

```json
{
  "esquema": "botonera-servicio/1",
  "id": "mi_api",                      // único; minúsculas, dígitos, guion bajo
  "nombre": "Mi API",
  "tipo": "servicio",                  // libre: servicio | monitor | maqueta | prueba … (los "monitor" van primero)
  "descripcion": "Una línea para el detalle.",
  "carpeta": "/ruta/absoluta",         // informativo
  "documentacion": "/ruta/LEEME.md",   // informativo
  "tarjeta": {
    "cmd": ["/ruta/python", "/ruta/estado.py", "estado"],
    "campo": "tarjeta",                // nombre del campo del JSON de salida (por defecto "tarjeta")
    "cada_segundos": 10                // mínimo 3
  },
  "acciones": { … },                   // ver abajo
  "archivos": { … },                   // informativo: rutas de log, pid, latido…
  "latido": { … }                      // informativo
}
```

Las rutas van **absolutas** (la Botonera no expande `~` dentro de `cmd`). Cualquier clave extra se ignora.

## La tarjeta (lo que imprime `tarjeta.cmd`)

```json
{
  "corriendo": true,
  "tarjeta": {
    "semaforo": "verde",                       // verde | amarillo | rojo | gris
    "titulo": "Mi API",
    "subtitulo": "Corriendo (pid 4121) · 14 peticiones hoy",
    "datos": [ {"etiqueta": "Última actividad", "valor": "hace 2 min"} ],
    "atencion": [ "3 errores en la última hora (ver registro)" ]
  }
}
```

| Campo | Uso en la página |
|---|---|
| `semaforo` | color del punto; `rojo`/`amarillo` resaltan el borde de la tarjeta compacta |
| `titulo` | respaldo del nombre: en la página manda el `nombre` de la ficha (así renombras algo sin tocar su script) |
| `subtitulo` | una línea bajo el nombre (2 líneas máx. en la compacta); si contiene "en curso", "iniciando" o "ejecutando", el punto parpadea |
| `datos[]` | pares etiqueta/valor ya formateados, en el detalle; una etiqueta `Estado` se omite (ya está en el subtítulo) |
| `atencion[]` | frases que piden acción; su cantidad aparece como marca "N avisos" en la compacta |

Significado sugerido: verde corriendo · amarillo requiere atención · rojo con problemas · gris detenido.
Si el comando falla o no imprime JSON, la tarjeta sale roja con el texto del error.

## Acciones

```json
"acciones": {
  "estado":    {"cmd": [...], "salida": "json"},                     // oculta; la usan otras herramientas
  "iniciar":   {"cmd": [...], "salida": "json"},
  "reiniciar": {"cmd": [...], "salida": "json"},                     // confirma siempre
  "detener":   {"cmd": [...], "salida": "json", "confirmar": true},  // confirma siempre
  "ver_log":   {"cmd": ["/usr/bin/open", "-a", "Console", "/ruta/log"]},
  "medir_ahora": {"cmd": [...], "salida": "json", "nota": "texto libre para quien lea la ficha"}
}
```

- Cada clave es un botón. Etiquetas conocidas: `iniciar`, `iniciar_sin_ventana`, `detener`, `reiniciar`, `ver_log`,
  `abrir`. Para el resto, la etiqueta es la clave con guiones bajos → espacios (`medir_ahora` → "Medir ahora").
- `confirmar: true` muestra un diálogo antes de ejecutar; `detener` y `reiniciar` confirman siempre.
- El comando puede imprimir `{"ok": true|false, "mensaje": "…"}`; si no imprime JSON, se muestra el texto.
  Código de salida 0 = ok cuando no hay JSON.
- Un `cmd` con marcadores `{n}`, `{nombre}`, `{motivo}`, `{params_json}` **no aparece como botón**: son para
  acciones con parámetro (aprobaciones). Los valores se validan antes de reemplazarse.
- Claves ocultas (no son botones): `estado`, `pendientes`, `ver`, `aprobar`, `aprobar_riesgo_alto`, `rechazar`,
  `lanzar`, `catalogo`, `trabajos`.

## Cola de aprobaciones (opcional)

Si tu servicio pide confirmación humana antes de hacer algo (ejecutar un script que escribió un agente, por
ejemplo), declara `pendientes` + `aprobar` y la Botonera pinta una sección **Aprobaciones pendientes** arriba.

`pendientes.cmd` imprime:

```json
{"pendientes": [
  {"numero": 12, "nombre": "tabla-pypi", "riesgo": "bajo|medio|alto", "solicitante": "quién lo pidió",
   "proposito": "qué hace", "dominios": ["pypi.org"],
   "avisos": [{"titulo": "Usa POST", "detalle": ["…"]}],
   "alertas_rojas": [{"titulo": "Instala paquetes", "detalle": ["pandas"]}]}
]}
```

Botones que se generan por cada pendiente: **Aprobar** (`aprobar` con `{n}`), **Aprobar riesgo alto**
(`aprobar_riesgo_alto` con `{n}`; exige escribir APROBAR), **Rechazar** (`rechazar` con `{n}` y `{motivo}`),
**Ver código** (`ver` con `{n}`, debe imprimir `{"analisis": {"riesgo": "…", "manifiesto": {...}}, "codigo": {"main.py": "…"}}`).

## Servicios web locales (sin ficha)

Aparte de las fichas, la Botonera lista por sí sola todo lo que escucha en un puerto TCP de tu usuario y
responde HTTP (`puertos.py`, con `lsof` y `ps`): título de la página, URL, proceso, carpeta y antigüedad,
con botones Abrir, Vista previa y Detener. No requiere configuración.

## Seguridad

- Escucha solo en `127.0.0.1` y rechaza otros `Host`.
- Un token por arranque va dentro de la página; sin él no hay API. Una web cualquiera abierta en tu
  navegador no puede pulsar tus botones.
- Solo ejecuta lo que está en las fichas, sin shell. Quien pueda escribir en la carpeta de registro puede
  definir comandos: mantenla fuera de cualquier carpeta que compartas con agentes o con otras personas.
