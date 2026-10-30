"""
comun.py — utilidades para los scripts de estado de la botonera (solo biblioteca estándar, Python 3.9+).

Cada script de servicio define un dict CONFIG y llama a ejecutar(CONFIG, calcular_extra).
Subcomandos:  estado (JSON con 'tarjeta')  ·  iniciar  ·  detener  ·  reiniciar  ·  ver_log
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LAUNCHCTL = os.environ.get("BOTONERA_LAUNCHCTL", "/bin/launchctl")


def expandir(p):
    return Path(os.path.expanduser(str(p)))


def hace(segundos):
    if segundos is None:
        return "nunca"
    s = int(max(0, segundos))
    if s < 90:
        return "hace %d s" % s
    if s < 5400:
        return "hace %d min" % (s // 60)
    if s < 172800:
        return "hace %d h" % (s // 3600)
    return "hace %d días" % (s // 86400)


def launchd(label):
    """Estado del agente de launchd: {'cargado', 'corriendo', 'pid', 'ultimo_codigo', 'error'}."""
    info = {"cargado": False, "corriendo": False, "pid": None, "ultimo_codigo": None, "error": None}
    if not os.path.exists(LAUNCHCTL):
        info["error"] = "launchctl no disponible en este equipo"
        return info
    try:
        r = subprocess.run([LAUNCHCTL, "print", "gui/%d/%s" % (os.getuid(), label)],
                           capture_output=True, text=True, timeout=8)
    except Exception as ex:
        info["error"] = str(ex)
        return info
    if r.returncode != 0:
        return info                       # no cargado
    info["cargado"] = True
    m = re.search(r"^\s*state = (\S+)", r.stdout, re.M)
    info["corriendo"] = bool(m and m.group(1) == "running")
    m = re.search(r"^\s*pid = (\d+)", r.stdout, re.M)
    info["pid"] = int(m.group(1)) if m else None
    m = re.search(r"^\s*last exit code = (-?\d+)", r.stdout, re.M)
    info["ultimo_codigo"] = int(m.group(1)) if m else None
    return info


def archivos_hoy(carpeta, patron="*.json"):
    """Cuántos archivos de la carpeta se modificaron hoy (hora local)."""
    d = expandir(carpeta)
    if not d.is_dir():
        return 0
    inicio = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    n = 0
    for p in d.glob(patron):
        try:
            if p.stat().st_mtime >= inicio:
                n += 1
        except OSError:
            pass
    return n


def en_espera(carpeta, viejos_s=120):
    """(total, cuántos llevan más de viejos_s sin atender) de los pedidos en la carpeta requests/."""
    d = expandir(carpeta)
    if not d.is_dir():
        return 0, 0
    ahora, total, viejos = time.time(), 0, 0
    for p in d.glob("*.json"):
        total += 1
        try:
            if ahora - p.stat().st_mtime > viejos_s:
                viejos += 1
        except OSError:
            pass
    return total, viejos


def cola_log(ruta, lineas=300):
    p = expandir(ruta)
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            tam = f.tell()
            f.seek(max(0, tam - 200_000))
            return f.read().decode("utf-8", "replace").splitlines()[-lineas:]
    except OSError:
        return []


RE_FECHA = re.compile(r"^(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d)")


def actividad(lineas, es_error, ventana_s=3600):
    """(segundos desde la última línea con fecha, errores dentro de la ventana). Fechas locales del registro."""
    ahora, ultima, errores, t = time.time(), None, 0, None
    for l in lineas:
        m = RE_FECHA.match(l)
        if m:
            try:
                t = datetime.fromisoformat(m.group(1).replace(" ", "T")).timestamp()
                ultima = t
            except ValueError:
                pass
        if t is not None and ahora - t <= ventana_s and es_error(l):
            errores += 1
    return (ahora - ultima if ultima else None), errores


def edad_archivo(ruta):
    try:
        return time.time() - expandir(ruta).stat().st_mtime
    except OSError:
        return None


def tarjeta_base(cfg, ld):
    """Semáforo y datos comunes de un servicio de launchd."""
    plist = expandir(cfg["plist"])
    atencion = []
    if ld["error"]:
        semaforo, sub = "gris", ld["error"]
    elif ld["corriendo"]:
        semaforo, sub = "verde", "Corriendo (pid %s)" % ld["pid"]
    elif ld["cargado"]:
        semaforo = "rojo"
        sub = "Cargado pero detenido" + (" (último código %s)" % ld["ultimo_codigo"] if ld["ultimo_codigo"] else "")
        atencion.append("launchd lo tiene cargado pero no está corriendo: prueba Reiniciar y revisa el registro")
    else:
        semaforo, sub = "gris", "Detenido (no cargado en launchd)"
        if not plist.exists():
            atencion.append("No encuentro %s: el botón Iniciar no funcionará hasta que exista" % cfg["plist"])
    datos = [{"etiqueta": "Estado", "valor": sub}, {"etiqueta": "Agente launchd", "valor": cfg["label"]}]
    return semaforo, sub, datos, atencion


def ejecutar(cfg, extra):
    """Punto de entrada común. extra(cfg, ld) -> (semaforo|None, datos[], atencion[], crudo{})."""
    accion = sys.argv[1] if len(sys.argv) > 1 else "estado"
    uid = os.getuid()
    destino = "gui/%d/%s" % (uid, cfg["label"])
    if accion == "estado":
        ld = launchd(cfg["label"])
        semaforo, sub, datos, atencion = tarjeta_base(cfg, ld)
        s2, d2, a2, crudo = extra(cfg, ld)
        if s2 and semaforo == "verde":
            semaforo = s2
        datos += d2
        atencion += a2
        print(json.dumps({"servicio": cfg["id"], "corriendo": ld["corriendo"], "launchd": ld, "crudo": crudo,
                          "tarjeta": {"semaforo": semaforo, "titulo": cfg["nombre"], "subtitulo": sub,
                                      "datos": datos, "atencion": atencion}}, ensure_ascii=False))
        sys.exit(0 if ld["corriendo"] else 1)

    def correr(args):
        r = subprocess.run([LAUNCHCTL] + args, capture_output=True, text=True, timeout=20)
        return {"cmd": "launchctl " + " ".join(args), "rc": r.returncode, "salida": (r.stdout + r.stderr).strip()[:500]}

    pasos = []
    if accion == "iniciar":
        if not launchd(cfg["label"])["cargado"]:
            plist = expandir(cfg["plist"])
            if not plist.exists():
                print(json.dumps({"ok": False, "mensaje": "no existe %s" % plist}, ensure_ascii=False))
                sys.exit(1)
            pasos.append(correr(["bootstrap", "gui/%d" % uid, str(plist)]))
        pasos.append(correr(["kickstart", destino]))
    elif accion == "reiniciar":
        pasos.append(correr(["kickstart", "-k", destino]))
    elif accion == "detener":
        # bootout descarga el agente; con KeepAlive, un simple kill lo haría reiniciar.
        pasos.append(correr(["bootout", destino]))
    elif accion == "ver_log":
        r = subprocess.run(["/usr/bin/open", "-a", "Console", str(expandir(cfg["log"]))], capture_output=True, text=True)
        print(json.dumps({"ok": r.returncode == 0, "mensaje": "abriendo el registro en Consola"}, ensure_ascii=False))
        sys.exit(r.returncode)
    else:
        sys.exit("acción desconocida: %s" % accion)
    time.sleep(1)
    ld = launchd(cfg["label"])
    ok = ld["corriendo"] if accion in ("iniciar", "reiniciar") else not ld["cargado"]
    print(json.dumps({"ok": ok, "accion": accion, "pasos": pasos, "launchd": ld}, ensure_ascii=False))
    sys.exit(0 if ok else 1)
