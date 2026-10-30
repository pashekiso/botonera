"""
puertos.py — descubre los servicios web que escuchan en este Mac (maquetas, servidores de desarrollo).

Usa `lsof` y `ps` (vienen con macOS) para listar los puertos TCP en escucha de TU usuario, prueba cada uno
con una petición HTTP corta a 127.0.0.1 y devuelve título de la página, proceso, carpeta y antigüedad.
Solo biblioteca estándar. Python 3.9+.
"""
import http.client
import os
import re
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

LSOF = "/usr/sbin/lsof" if os.path.exists("/usr/sbin/lsof") else "/usr/bin/lsof"
PS = "/bin/ps" if os.path.exists("/bin/ps") else "/usr/bin/ps"
# Ejecutables de apps y del sistema: se muestran aparte y sin botón Detener.
RUTAS_APPS = ("/System/", "/Applications/", "/usr/libexec/", "/usr/sbin/", "/Library/", "/sbin/",
              os.path.expanduser("~/Library/"), os.path.expanduser("~/Applications/"))
RE_TITULO = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)

_cache = {"t": 0, "datos": None}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=12)


def _lsof_escucha():
    """{pid: {"comando": str, "direcciones": [(host, puerto)]}} de los sockets TCP en LISTEN del usuario."""
    try:
        r = subprocess.run([LSOF, "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-u", str(os.getuid()), "-F", "pcn"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise RuntimeError("no pude ejecutar lsof: %s" % ex)
    out, pid = {}, None
    for l in r.stdout.splitlines():
        if not l:
            continue
        k, v = l[0], l[1:]
        if k == "p":
            pid = int(v)
            out.setdefault(pid, {"comando": "", "direcciones": []})
        elif k == "c" and pid:
            out[pid]["comando"] = v
        elif k == "n" and pid:
            host, _, puerto = v.rpartition(":")
            if puerto.isdigit():
                par = (host.strip("[]"), int(puerto))
                if par not in out[pid]["direcciones"]:
                    out[pid]["direcciones"].append(par)
    return out


def _ps(pids):
    if not pids:
        return {}
    try:
        r = subprocess.run([PS, "-o", "pid=,etime=,command=", "-p", ",".join(str(p) for p in pids)],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    out = {}
    for l in r.stdout.splitlines():
        partes = l.strip().split(None, 2)
        if len(partes) >= 2 and partes[0].isdigit():
            out[int(partes[0])] = {"etime": partes[1], "linea": partes[2] if len(partes) > 2 else ""}
    return out


def _cwd(pids):
    if not pids:
        return {}
    try:
        r = subprocess.run([LSOF, "-a", "-d", "cwd", "-p", ",".join(str(p) for p in pids), "-Fpn"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    out, pid = {}, None
    for l in r.stdout.splitlines():
        if l.startswith("p"):
            pid = int(l[1:])
        elif l.startswith("n") and pid:
            out[pid] = l[1:]
    return out


def _etime_a_texto(e):
    """'1-02:03:04' / '02:03:04' / '03:04' -> texto corto."""
    try:
        dias = 0
        if "-" in e:
            d, e = e.split("-", 1)
            dias = int(d)
        partes = [int(x) for x in e.split(":")]
        while len(partes) < 3:
            partes.insert(0, 0)
        h, m, s = partes
        total = dias * 86400 + h * 3600 + m * 60 + s
    except ValueError:
        return e, None
    if total < 90:
        return "%d s" % total, total
    if total < 5400:
        return "%d min" % (total // 60), total
    if total < 172800:
        return "%d h %02d min" % (total // 3600, total % 3600 // 60), total
    return "%d días" % (total // 86400), total


def _probar(puerto):
    """GET / a 127.0.0.1:puerto. -> {"web": bool, "estado": int, "titulo": str, "servidor": str}"""
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=1.5)
    try:
        c.request("GET", "/", headers={"Host": "localhost:%d" % puerto, "User-Agent": "botonera",
                                       "Accept": "text/html,*/*"})
        r = c.getresponse()
        cuerpo = r.read(65536)
        m = RE_TITULO.search(cuerpo)
        titulo = re.sub(r"\s+", " ", m.group(1).decode("utf-8", "replace")).strip()[:120] if m else ""
        return {"web": True, "estado": r.status, "titulo": titulo, "servidor": (r.getheader("Server") or "")[:60],
                "tipo": (r.getheader("Content-Type") or "").split(";")[0]}
    except Exception:
        return {"web": False}
    finally:
        c.close()


def _corto(linea, n=110):
    linea = linea.replace(os.path.expanduser("~"), "~")
    return linea if len(linea) <= n else linea[:n - 1] + "…"


def escanear(propio_pid=None, ttl=5):
    with _lock:
        if _cache["datos"] is not None and time.time() - _cache["t"] < ttl:
            return _cache["datos"]
    try:
        escucha = _lsof_escucha()
    except RuntimeError as ex:
        return {"ok": False, "mensaje": str(ex), "servicios": []}
    pids = sorted(escucha)
    info, cwds = _ps(pids), _cwd(pids)
    filas = []
    for pid, e in escucha.items():
        for puerto in sorted({p for _, p in e["direcciones"]}):
            hosts = [h for h, p in e["direcciones"] if p == puerto]
            filas.append((pid, e["comando"], puerto, hosts))
    pruebas = {puerto: _pool.submit(_probar, puerto) for _, _, puerto, _ in filas}
    servicios = []
    for pid, comando, puerto, hosts in filas:
        try:
            prueba = pruebas[puerto].result(timeout=4)
        except Exception:
            prueba = {"web": False}
        linea = (info.get(pid) or {}).get("linea", comando)
        ejecutable = linea.split(" ")[0] if linea else ""
        es_app = ejecutable.startswith(RUTAS_APPS)
        activo, activo_s = _etime_a_texto((info.get(pid) or {}).get("etime", ""))
        expuesto = any(h in ("*", "0.0.0.0", "::", "") for h in hosts) or \
            any(h not in ("127.0.0.1", "::1", "localhost") for h in hosts)
        servicios.append({
            "pid": pid, "puerto": puerto, "proceso": comando, "comando": _corto(linea),
            "carpeta": (cwds.get(pid) or "").replace(os.path.expanduser("~"), "~"),
            "activo": activo, "activo_s": activo_s, "escucha": hosts, "expuesto": expuesto,
            "url": "http://localhost:%d/" % puerto, "es_app": es_app, "es_botonera": pid == propio_pid,
            **prueba,
        })
    servicios.sort(key=lambda s: (not s["web"], s["es_app"], s["puerto"]))
    datos = {"ok": True, "servicios": servicios, "t": time.strftime("%H:%M:%S")}
    with _lock:
        _cache.update(t=time.time(), datos=datos)
    return datos


def detener(pid, puerto, forzar=False, propio_pid=None):
    """Envía SIGTERM (o SIGKILL) solo si ese pid sigue escuchando en ese puerto y no es una app del sistema."""
    if pid == propio_pid or pid == os.getpid():
        return {"ok": False, "mensaje": "es la propia botonera: usa su botón Detener"}
    try:
        actual = _lsof_escucha()
    except RuntimeError as ex:
        return {"ok": False, "mensaje": str(ex)}
    if pid not in actual or puerto not in {p for _, p in actual[pid]["direcciones"]}:
        return {"ok": False, "mensaje": "el proceso %d ya no escucha en el puerto %d" % (pid, puerto)}
    linea = (_ps([pid]).get(pid) or {}).get("linea", "")
    if linea.split(" ")[0].startswith(RUTAS_APPS):
        return {"ok": False, "mensaje": "es una app o servicio del sistema; ciérrala desde la propia app"}
    try:
        os.kill(pid, signal.SIGKILL if forzar else signal.SIGTERM)
    except ProcessLookupError:
        return {"ok": True, "mensaje": "ya había terminado"}
    except PermissionError:
        return {"ok": False, "mensaje": "sin permiso para detener el proceso %d" % pid}
    for _ in range(15):
        time.sleep(0.2)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            with _lock:
                _cache["datos"] = None
            return {"ok": True, "mensaje": "detenido (pid %d, puerto %d)" % (pid, puerto)}
    with _lock:
        _cache["datos"] = None
    return {"ok": False, "sigue_vivo": True,
            "mensaje": "el proceso %d no terminó con SIGTERM; usa Forzar si quieres terminarlo" % pid}
