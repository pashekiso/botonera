#!/usr/bin/env python3
"""
ejemplo_launchd.py — plantilla de script de estado para un servicio que corre bajo launchd.

Copia este archivo con el nombre de tu servicio (p. ej. estados/mi_api.py), ajusta CONFIG y, si quieres,
agrega datos propios en extra(). Luego deja una ficha en la carpeta de registro que apunte a él
(ver fichas-ejemplo/launchd-servicio.json).

  uso: mi_api.py estado | iniciar | detener | reiniciar | ver_log
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun as C  # noqa: E402

CONFIG = {
    "id": "mi_api",                                   # id de la ficha
    "nombre": "Mi API",                               # título de la tarjeta
    "label": "local.mi-api",                          # Label del plist
    "plist": "~/Library/LaunchAgents/local.mi-api.plist",
    "carpeta": "~/dev/mi_api",
    "log": "~/dev/mi_api/servicio.log",
}


def extra(cfg, ld):
    """Datos adicionales para la tarjeta. Devuelve (semaforo_o_None, datos[], atencion[], crudo{}).

    `ld` trae el estado de launchd: {'cargado', 'corriendo', 'pid', 'ultimo_codigo', 'error'}.
    Si devuelves un semáforo ('amarillo' o 'rojo') se usa solo cuando el servicio está corriendo.
    """
    lineas = C.cola_log(cfg["log"])
    ultima, errores = C.actividad(lineas, lambda l: " ERROR " in l)
    datos = [{"etiqueta": "Última actividad", "valor": C.hace(ultima)}]
    atencion, semaforo = [], None
    if errores:
        atencion.append("%d error(es) en la última hora (ver registro)" % errores)
        semaforo = "amarillo"
    return semaforo, datos, atencion, {"ultima_actividad_s": ultima, "errores_recientes": errores}


if __name__ == "__main__":
    C.ejecutar(CONFIG, extra)
