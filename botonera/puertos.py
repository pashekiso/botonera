"""
puertos.py — descubre los servicios web que escuchan en este equipo (maquetas, servidores de desarrollo).

macOS: `lsof` y `ps`. Windows (beta): `netstat -ano` y PowerShell (Win32_Process) para la línea de comando.
Lista los puertos TCP en escucha de TU usuario, prueba cada uno con una petición HTTP corta a 127.0.0.1 y
devuelve título de la página, proceso, carpeta (macOS) y antigüedad. Solo biblioteca estándar. Python 3.9+.
"""
import json
import sys
from datetime import datetime
import http.client
import os
import re
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

WIN = sys.platform == "win32"
SUBPROC = {"creationflags": subprocess.CREATE_NO_WINDOW} if WIN else {}
LSOF = "/usr/sbin/lsof" if os.path.exists("/usr/sbin/lsof") else "/usr/bin/lsof"
PS = "/bin/ps" if os.path.exists("/bin/ps") else "/usr/bin/ps"
# Ejecutables de apps y del sistema: se muestran aparte y sin botón Detener.
if WIN:
    _ld = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    RUTAS_APPS = tuple(r.lower() for r in (
        os.environ.get("SystemRoot", "C:\\Windows") + "\\", os.environ.get("ProgramFiles", "C:\\Program Files") + "\\",
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)") + "\\", os.path.join(_ld, "Programs") + "\\",
        os.path.join(_ld, "Microsoft") + "\\"))
    RE_HOME = re.compile(re.escape(os.path.expanduser("~")) + r"\\(?!AppData\\)", re.I)   # un script bajo el perfil del usuario = desarrollo
else:
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


def _netstat_escucha():
    """Windows: {pid: {"comando": "", "direcciones": [(host, puerto)]}} de los sockets TCP en LISTENING."""
    try:
        r = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, errors="replace", timeout=15, **SUBPROC)
        r6 = subprocess.run(["netstat", "-ano", "-p", "tcpv6"], capture_output=True, text=True, errors="replace", timeout=15, **SUBPROC)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise RuntimeError("no pude ejecutar netstat: %s" % ex)
    out = {}
    for l in (r.stdout + r6.stdout).splitlines():
        partes = l.split()
        if len(partes) < 5 or partes[0].upper() != "TCP" or partes[3].upper() != "LISTENING":
            continue
        local, pid = partes[1], partes[4]
        host, _, puerto = local.rpartition(":")
        if not (puerto.isdigit() and pid.isdigit()):
            continue
        par = (host.strip("[]"), int(puerto))
        d = out.setdefault(int(pid), {"comando": "", "direcciones": []})
        if par not in d["direcciones"]:
            d["direcciones"].append(par)
    return out


def _powershell(script, timeout=20):
    script = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; " + script
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, **SUBPROC)
    return r.stdout


def _procesos_win(pids):
    """{pid: {"nombre", "exe", "linea", "creado": datetime|None}} vía Win32_Process (PowerShell)."""
    if not pids:
        return {}
    filtro = " OR ".join("ProcessId=%d" % p for p in pids)
    script = ("Get-CimInstance Win32_Process -Filter '%s' | Select-Object ProcessId,Name,ExecutablePath,CommandLine,"
              "@{n='Creado';e={$_.CreationDate.ToString('yyyy-MM-ddTHH:mm:ss')}} | ConvertTo-Json -Compress" % filtro)
    try:
        txt = _powershell(script).strip()
        datos = json.loads(txt) if txt else []
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}
    if isinstance(datos, dict):
        datos = [datos]
    out = {}
    for d in datos:
        try:
            creado = datetime.fromisoformat(d["Creado"]) if d.get("Creado") else None
        except (ValueError, TypeError):
            creado = None
        out[int(d["ProcessId"])] = {"nombre": d.get("Name") or "", "exe": d.get("ExecutablePath") or "",
                                    "linea": d.get("CommandLine") or d.get("Name") or "", "creado": creado}
    return out


def _edad_texto(segundos):
    s = int(max(0, segundos))
    if s < 90:
        return "%d s" % s, s
    if s < 5400:
        return "%d min" % (s // 60), s
    if s < 172800:
        return "%d h %02d min" % (s // 3600, s % 3600 // 60), s
    return "%d días" % (s // 86400), s


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
        escucha = _netstat_escucha() if WIN else _lsof_escucha()
    except RuntimeError as ex:
        return {"ok": False, "mensaje": str(ex), "servicios": []}
    pids = sorted(escucha)
    if WIN:
        pw = _procesos_win(pids)
        info, cwds = {}, {}
        for pid, d in pw.items():
            edad = (datetime.now() - d["creado"]).total_seconds() if d["creado"] else None
            info[pid] = {"etime": edad, "linea": d["linea"], "nombre": d["nombre"], "exe": d["exe"]}
            escucha[pid]["comando"] = d["nombre"]
        for pid in pids:                       # procesos del sistema que PowerShell no puede leer (otro usuario)
            if pid not in info:
                info[pid] = {"etime": None, "linea": "", "nombre": "pid %d" % pid, "exe": os.environ.get("SystemRoot", "C:\\Windows") + "\\"}
                escucha[pid]["comando"] = "sistema"
    else:
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
        if WIN:
            exe = ((info.get(pid) or {}).get("exe") or linea.split(" ")[0]).lower()
            es_app = exe.startswith(RUTAS_APPS) and not RE_HOME.search(linea or "")
            et = (info.get(pid) or {}).get("etime")
            activo, activo_s = _edad_texto(et) if et is not None else ("?", None)
        else:
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
        actual = _netstat_escucha() if WIN else _lsof_escucha()
    except RuntimeError as ex:
        return {"ok": False, "mensaje": str(ex)}
    if pid not in actual or puerto not in {p for _, p in actual[pid]["direcciones"]}:
        return {"ok": False, "mensaje": "el proceso %d ya no escucha en el puerto %d" % (pid, puerto)}
    if WIN:
        d = _procesos_win([pid]).get(pid) or {}
        exe, linea = (d.get("exe") or "").lower(), d.get("linea") or ""
        if not d or (exe.startswith(RUTAS_APPS) and not RE_HOME.search(linea)):
            return {"ok": False, "mensaje": "es una app o servicio del sistema; ciérrala desde la propia app"}
        # taskkill /T cierra también los hijos (los servidores de desarrollo suelen tenerlos); /F fuerza.
        args = ["taskkill", "/PID", str(pid), "/T"] + (["/F"] if forzar else [])
        try:
            r = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=15, **SUBPROC)
        except (OSError, subprocess.TimeoutExpired) as ex:
            return {"ok": False, "mensaje": "taskkill: %s" % ex}
        for _ in range(15):
            time.sleep(0.2)
            if pid not in _netstat_escucha():
                with _lock:
                    _cache["datos"] = None
                return {"ok": True, "mensaje": "detenido (pid %d, puerto %d)" % (pid, puerto)}
        with _lock:
            _cache["datos"] = None
        return {"ok": False, "sigue_vivo": True, "mensaje": "el proceso %d no cerró; usa Forzar para terminarlo (%s)" % (pid, (r.stdout + r.stderr).strip()[:120])}
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
