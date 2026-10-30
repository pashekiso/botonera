#!/usr/bin/env python3
"""
botonera.py — panel local con el estado de todo lo que corre en el Mac (servicios, maquetas, pruebas).

Lee las fichas (*.json con "esquema": "botonera-servicio/1") de la carpeta de registro, ejecuta el
comando "tarjeta" de cada una y lo muestra en una página web local con semáforo, datos, avisos,
botones y, si alguna ficha lo declara, una cola de aprobaciones.

  botonera.py iniciar            instala (si hace falta) y arranca el servicio de usuario launchd; abre el navegador
  botonera.py detener            detiene el servicio (o el proceso suelto, si corre en una Terminal)
  botonera.py reiniciar          reinicia el servicio
  botonera.py servicio instalar|desinstalar   escribe/quita ~/Library/LaunchAgents/local.botonera.plist
  botonera.py servir [--abrir]   modo ventana: corre en esta Terminal (para depurar)
  botonera.py tarjeta            estado de la propia botonera (JSON, para su ficha)
  botonera.py ver_log            abre var/botonera.log en Consola
  botonera.py fichas             (re)escribe la ficha de la propia botonera en la carpeta de registro

Solo biblioteca estándar. Python 3.9+.
"""
import json
import os
import plistlib
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import puertos  # noqa: E402

BASE = Path(os.environ.get("BOTONERA_HOME") or Path(__file__).resolve().parent).resolve()
VAR = BASE / "var"
DEFECTO = {"puerto": 8790, "registro": str(BASE / "servicios"), "tarjeta_min_s": 3, "timeout_tarjeta_s": 15,
           "timeout_accion_s": 90}
ESQUEMA = "botonera-servicio/"
LABEL = "local.botonera"
PLIST = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")
LAUNCHCTL = "/bin/launchctl"
LOG = VAR / "botonera.log"
OCULTAS = {"estado", "pendientes", "ver", "aprobar", "aprobar_riesgo_alto", "rechazar", "lanzar", "catalogo",
           "trabajos"}
ETIQUETAS = {"iniciar": "Iniciar", "iniciar_sin_ventana": "Iniciar sin ventana", "detener": "Detener",
             "reiniciar": "Reiniciar", "ver_log": "Ver registro", "abrir": "Abrir"}
CONFIRMAR = {"detener", "reiniciar"}
VALIDADORES = {
    "n": re.compile(r"^#?[A-Za-z0-9_-]{1,64}$"),
    "nombre": re.compile(r"^[a-z0-9][a-z0-9-]{1,59}$"),
}


def cargar_config():
    cfg = dict(DEFECTO)
    try:
        cfg.update({k: v for k, v in json.loads((BASE / "config.json").read_text(encoding="utf-8")).items()
                    if not k.startswith("_")})
    except (OSError, ValueError):
        pass
    cfg["registro"] = os.path.expanduser(cfg["registro"])
    return cfg


CFG = cargar_config()


def log(texto):
    print("%s  %s" % (datetime.now().strftime("%H:%M:%S"), texto), flush=True)


def escribir_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name("." + p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


# --------------------------------------------------------------------------- #
# Fichas
# --------------------------------------------------------------------------- #
def fichas():
    out = []
    for f in sorted(Path(CFG["registro"]).glob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(m, dict) and str(m.get("esquema", "")).startswith(ESQUEMA) and m.get("id"):
            m["_archivo"] = str(f)
            out.append(m)
    return out


def correr(cmd, timeout):
    """Ejecuta una lista de argumentos (sin shell). Devuelve (rc, objeto_json_o_None, texto)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 124, None, "no respondió en %s s" % timeout
    except (OSError, ValueError) as ex:
        return 127, None, "%s: %s" % (type(ex).__name__, ex)
    try:
        return r.returncode, json.loads(r.stdout), r.stdout
    except ValueError:
        return r.returncode, None, (r.stdout + r.stderr).strip()[-2000:]


class Estado:
    """Caché de tarjetas y pendientes, refrescadas en paralelo según cada_segundos de cada ficha."""

    def __init__(self):
        self.tarjetas = {}       # id -> {"t": epoch, "tarjeta": {...}}
        self.pendientes = {}     # id -> {"t": epoch, "lista": [...]}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=8)

    def _tarjeta(self, m):
        t = m.get("tarjeta") or {}
        if not t.get("cmd"):
            return {"semaforo": "gris", "titulo": m.get("nombre", m["id"]), "subtitulo": "La ficha no define tarjeta.cmd",
                    "datos": [], "atencion": []}
        rc, obj, texto = correr(t["cmd"], CFG["timeout_tarjeta_s"])
        if isinstance(obj, dict) and isinstance(obj.get(t.get("campo", "tarjeta")), dict):
            return obj[t.get("campo", "tarjeta")]
        return {"semaforo": "rojo", "titulo": m.get("nombre", m["id"]), "subtitulo": "No pude leer su estado",
                "datos": [], "atencion": [texto[:300] or "código %s" % rc]}

    def _pendientes(self, m):
        a = (m.get("acciones") or {}).get("pendientes")
        if not a:
            return []
        rc, obj, _ = correr(a["cmd"], CFG["timeout_tarjeta_s"])
        lista = (obj or {}).get("pendientes") if isinstance(obj, dict) else None
        return lista if isinstance(lista, list) else []

    def invalidar(self, sid):
        with self.lock:
            self.tarjetas.pop(sid, None)
            self.pendientes.pop(sid, None)

    def leer(self):
        ms = fichas()
        ahora = time.time()
        trabajos = {}
        for m in ms:
            cada = max(float(CFG["tarjeta_min_s"]), float((m.get("tarjeta") or {}).get("cada_segundos", 5)))
            c = self.tarjetas.get(m["id"])
            if not c or ahora - c["t"] >= cada:
                trabajos[("t", m["id"])] = self.pool.submit(self._tarjeta, m)
            if (m.get("acciones") or {}).get("pendientes"):
                p = self.pendientes.get(m["id"])
                if not p or ahora - p["t"] >= 2:
                    trabajos[("p", m["id"])] = self.pool.submit(self._pendientes, m)
        for (tipo, sid), fut in trabajos.items():
            try:
                valor = fut.result(timeout=CFG["timeout_tarjeta_s"] + 2)
            except Exception as ex:
                valor = ({"semaforo": "rojo", "titulo": sid, "subtitulo": "Error leyendo estado", "datos": [],
                          "atencion": [str(ex)]} if tipo == "t" else [])
            with self.lock:
                (self.tarjetas if tipo == "t" else self.pendientes)[sid] = \
                    {"t": time.time(), ("tarjeta" if tipo == "t" else "lista"): valor}
        servicios, pendientes = [], []
        for m in ms:
            acciones = m.get("acciones") or {}
            servicios.append({
                "id": m["id"], "nombre": m.get("nombre", m["id"]), "tipo": m.get("tipo", "servicio"),
                "descripcion": m.get("descripcion", ""),
                "tarjeta": (self.tarjetas.get(m["id"]) or {}).get("tarjeta"),
                "actualizado": datetime.fromtimestamp((self.tarjetas.get(m["id"]) or {}).get("t", ahora)).strftime("%H:%M:%S"),
                "botones": [{"accion": k, "etiqueta": ETIQUETAS.get(k, k.replace("_", " ").capitalize()),
                             "confirmar": bool(v.get("confirmar")) or k in CONFIRMAR or bool(v.get("aviso")),
                             "aviso": str(v.get("aviso") or "")[:600]}
                            for k, v in acciones.items() if k not in OCULTAS and not re.search(r"\{\w+\}", " ".join(v.get("cmd", [])))],
                "aprueba": bool(acciones.get("pendientes") and acciones.get("aprobar")),
            })
            for p in (self.pendientes.get(m["id"]) or {}).get("lista", []):
                if isinstance(p, dict):
                    pendientes.append(dict(p, servicio=m["id"], servicio_nombre=m.get("nombre", m["id"])))
        return {"ahora": datetime.now().strftime("%H:%M:%S"), "registro": CFG["registro"],
                "servicios": servicios, "pendientes": pendientes}


ESTADO = Estado()


def rellenar(cmd, valores):
    out = []
    for arg in cmd:
        def reemplazo(m):
            k = m.group(1)
            if k not in valores:
                raise ValueError("falta el valor '%s'" % k)
            return valores[k]
        out.append(re.sub(r"\{(\w+)\}", reemplazo, str(arg)))
    return out


def validar(valores):
    limpio = {}
    for k, v in (valores or {}).items():
        v = str(v)
        if k in VALIDADORES:
            if not VALIDADORES[k].match(v):
                raise ValueError("valor inválido para %s" % k)
            limpio[k] = v.lstrip("#")
        elif k == "motivo":
            limpio[k] = " ".join(v.split())[:200] or "rechazado desde la botonera"
        elif k == "params_json":
            obj = json.loads(v or "{}")
            if not isinstance(obj, dict):
                raise ValueError("params_json debe ser un objeto JSON")
            limpio[k] = json.dumps(obj, ensure_ascii=False)
        else:
            raise ValueError("valor no soportado: %s" % k)
    return limpio


def accion(sid, nombre, valores):
    m = next((f for f in fichas() if f["id"] == sid), None)
    if not m:
        return 404, {"ok": False, "mensaje": "no hay ficha para %s" % sid}
    a = (m.get("acciones") or {}).get(nombre)
    if not a or not a.get("cmd") or nombre == "estado":
        return 400, {"ok": False, "mensaje": "%s no tiene la acción %s" % (sid, nombre)}
    try:
        cmd = rellenar(a["cmd"], validar(valores))
    except (ValueError, TypeError) as ex:
        return 400, {"ok": False, "mensaje": str(ex)}
    rc, obj, texto = correr(cmd, CFG["timeout_accion_s"])
    ESTADO.invalidar(sid)
    respuesta = obj if isinstance(obj, dict) else {"texto": texto}
    respuesta.setdefault("ok", rc == 0)
    respuesta["rc"] = rc
    if nombre != "ver":
        log("%s · %s %s → %s" % (sid, nombre, json.dumps(valores, ensure_ascii=False) if valores else "",
                                 "ok" if respuesta.get("ok") else "falló (%s)" % (respuesta.get("mensaje") or texto)[:120]))
    return 200, respuesta


# --------------------------------------------------------------------------- #
# Servidor HTTP (solo 127.0.0.1, con token por arranque)
# --------------------------------------------------------------------------- #
TOKEN = secrets.token_urlsafe(24)


class Manejador(BaseHTTPRequestHandler):
    server_version = "botonera/1"

    def log_message(self, *a):
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").lower()
        return host in ("127.0.0.1:%d" % CFG["puerto"], "localhost:%d" % CFG["puerto"])

    def _enviar(self, codigo, cuerpo, tipo="application/json; charset=utf-8"):
        datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                         "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; "
                         "frame-src http://localhost:* http://127.0.0.1:*")
        self.end_headers()
        self.wfile.write(datos)

    def _autorizado(self):
        return self._host_ok() and secrets.compare_digest(self.headers.get("X-Botonera-Token", ""), TOKEN)

    def do_GET(self):
        if not self._host_ok():
            return self._enviar(403, {"ok": False, "mensaje": "host no permitido"})
        u = urlparse(self.path)
        if u.path == "/favicon.ico":
            return self._enviar(204, b"", "image/x-icon")
        if u.path in ("/", "/index.html"):
            html = (BASE / "pagina.html").read_text(encoding="utf-8").replace("{{TOKEN}}", TOKEN)
            return self._enviar(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if not self._autorizado():
            return self._enviar(403, {"ok": False, "mensaje": "token inválido; recarga la página"})
        if u.path == "/api/estado":
            return self._enviar(200, ESTADO.leer())
        if u.path == "/api/puertos":
            return self._enviar(200, puertos.escanear(os.getpid()))
        if u.path == "/api/ver":
            q = parse_qs(u.query)
            codigo, r = accion((q.get("id") or [""])[0], "ver", {"n": (q.get("n") or [""])[0]})
            return self._enviar(codigo, r)
        return self._enviar(404, {"ok": False})

    def do_POST(self):
        if not self._autorizado():
            return self._enviar(403, {"ok": False, "mensaje": "no autorizado"})
        ruta = urlparse(self.path).path
        if ruta == "/api/detener_puerto":
            d = {}
            try:
                largo = min(int(self.headers.get("Content-Length") or 0), 2000)
                d = json.loads(self.rfile.read(largo) or b"{}")
                r = puertos.detener(int(d["pid"]), int(d["puerto"]), bool(d.get("forzar")), os.getpid())
            except (ValueError, TypeError, KeyError) as ex:
                r = {"ok": False, "mensaje": "petición inválida: %s" % ex}
            log("puerto %s (pid %s) · %s → %s" % (d.get("puerto") if isinstance(d, dict) else "?",
                                                   d.get("pid") if isinstance(d, dict) else "?",
                                                   "forzar" if isinstance(d, dict) and d.get("forzar") else "detener",
                                                   r.get("mensaje")))
            return self._enviar(200, r)
        if ruta != "/api/accion":
            return self._enviar(404, {"ok": False})
        try:
            largo = min(int(self.headers.get("Content-Length") or 0), 20000)
            datos = json.loads(self.rfile.read(largo) or b"{}")
            codigo, r = accion(str(datos.get("id", "")), str(datos.get("accion", "")), datos.get("valores") or {})
        except (ValueError, TypeError) as ex:
            codigo, r = 400, {"ok": False, "mensaje": str(ex)}
        return self._enviar(codigo, r)


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return                      # el navegador cerró la pestaña a mitad de respuesta
        super().handle_error(request, client_address)


def url():
    return "http://127.0.0.1:%d/" % CFG["puerto"]


def servir(abrir):
    VAR.mkdir(parents=True, exist_ok=True)
    try:
        srv = Servidor(("127.0.0.1", CFG["puerto"]), Manejador)
    except OSError as ex:
        print("No pude abrir el puerto %d (%s). ¿Ya está corriendo? Abre %s" % (CFG["puerto"], ex, url()))
        if abrir and sys.platform == "darwin":
            subprocess.run(["/usr/bin/open", url()])
        sys.exit(3)
    escribir_json(VAR / "botonera.pid", {"pid": os.getpid(), "url": url(), "iniciado": datetime.now().astimezone().isoformat(timespec="seconds")})
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print("═" * 70)
    print(" Botonera  ·  %s" % url())
    print(" registro de fichas: %s" % CFG["registro"])
    print(" Cierra esta ventana (o Ctrl+C) para detenerla." if sys.stdout.isatty() else " servicio launchd %s" % LABEL)
    print("═" * 70, flush=True)
    for m in fichas():
        log("ficha: %s (%s)" % (m["id"], m.get("tipo", "servicio")))
    if abrir and sys.platform == "darwin":
        threading.Timer(0.8, lambda: subprocess.run(["/usr/bin/open", url()])).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            (VAR / "botonera.pid").unlink()
        except OSError:
            pass
        log("botonera detenida")


def tarjeta_propia():
    pid, vivo, ld = pid_archivo(), puerto_vivo(), launchd_estado()
    n = len(fichas())
    modo = ("servicio launchd %s" % LABEL) if ld["corriendo"] else ("ventana de Terminal" if vivo else ("servicio cargado pero detenido" if ld["cargado"] else "sin servicio instalado"))
    atencion = []
    if vivo and not ld["corriendo"]:
        atencion.append("Corre en una ventana de Terminal: con Iniciar pasa a ser un servicio que arranca solo al iniciar sesión")
    if ld["cargado"] and not vivo:
        atencion.append("launchd lo tiene cargado pero no responde: prueba Reiniciar y revisa el registro")
    t = {"semaforo": "verde" if vivo else ("rojo" if ld["cargado"] else "gris"), "titulo": "Botonera",
         "subtitulo": ("Corriendo en %s" % url()) if vivo else "Detenida",
         "datos": [{"etiqueta": "Modo", "valor": modo},
                   {"etiqueta": "Fichas registradas", "valor": str(n)},
                   {"etiqueta": "Registro", "valor": CFG["registro"]},
                   {"etiqueta": "Registro de actividad", "valor": str(LOG)}] + ([{"etiqueta": "PID", "valor": str(pid)}] if vivo and pid else []),
         "atencion": atencion}
    print(json.dumps({"corriendo": vivo, "tarjeta": t}, ensure_ascii=False))
    sys.exit(0 if vivo else 1)


# --------------------------------------------------------------------------- #
# Servicio de usuario (launchd): arranca solo al iniciar sesión, sin ventana
# --------------------------------------------------------------------------- #
def _launchctl(*args, timeout=20):
    try:
        r = subprocess.run([LAUNCHCTL] + list(args), capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as ex:
        return 1, str(ex)


def launchd_estado():
    """{'cargado', 'corriendo', 'pid'} del agente local.botonera (todo False/None si launchd no existe)."""
    info = {"cargado": False, "corriendo": False, "pid": None}
    if not os.path.exists(LAUNCHCTL):
        return info
    rc, out = _launchctl("print", "gui/%d/%s" % (os.getuid(), LABEL), timeout=8)
    if rc != 0:
        return info
    info["cargado"] = True
    m = re.search(r"^\s*state = (\S+)", out, re.M)
    info["corriendo"] = bool(m and m.group(1) == "running")
    m = re.search(r"^\s*pid = (\d+)", out, re.M)
    info["pid"] = int(m.group(1)) if m else None
    return info


def puerto_vivo():
    try:
        with socket.create_connection(("127.0.0.1", CFG["puerto"]), timeout=1):
            return True
    except OSError:
        return False


def pid_archivo():
    try:
        return int(json.loads((VAR / "botonera.pid").read_text(encoding="utf-8"))["pid"])
    except (OSError, ValueError, KeyError):
        return None


def _rotar_log():
    try:
        if LOG.exists() and LOG.stat().st_size > 5_000_000:
            os.replace(LOG, LOG.with_suffix(".log.1"))
    except OSError:
        pass


def servicio_instalar(silencioso=False):
    """Escribe el plist, detiene una botonera suelta (modo ventana) si la hay y carga el agente."""
    VAR.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    _rotar_log()
    with open(PLIST, "wb") as f:
        plistlib.dump({
            "Label": LABEL,
            "ProgramArguments": [sys.executable, str(BASE / "botonera.py"), "servir"],
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            "WorkingDirectory": str(BASE),
            "StandardOutPath": str(LOG),
            "StandardErrorPath": str(LOG),
            "ProcessType": "Interactive",
        }, f)
    _launchctl("bootout", "gui/%d/%s" % (os.getuid(), LABEL))
    # Si hay una botonera corriendo en una Terminal, se detiene para que el servicio tome el puerto.
    pid = pid_archivo()
    if pid and puerto_vivo():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(20):
            if not puerto_vivo():
                break
            time.sleep(0.25)
    rc, out = _launchctl("bootstrap", "gui/%d" % os.getuid(), str(PLIST))
    for _ in range(20):
        if puerto_vivo():
            break
        time.sleep(0.25)
    res = {"ok": puerto_vivo(), "plist": str(PLIST), "url": url(), "launchd": launchd_estado(),
           "mensaje": "servicio %s corriendo en %s" % (LABEL, url()) if puerto_vivo() else "bootstrap rc=%s: %s" % (rc, out[:300])}
    if not silencioso:
        print(json.dumps(res, ensure_ascii=False))
    return res


def servicio_desinstalar():
    _launchctl("bootout", "gui/%d/%s" % (os.getuid(), LABEL))
    try:
        PLIST.unlink()
    except OSError:
        pass
    print(json.dumps({"ok": True, "mensaje": "servicio %s descargado y plist borrado" % LABEL}))


def iniciar(abrir=True):
    """Arranca el servicio (instalándolo si no existe) y abre el navegador."""
    if sys.platform != "darwin":
        print(json.dumps({"ok": False, "mensaje": "el servicio launchd es solo para macOS; usa 'servir'"}))
        sys.exit(1)
    if puerto_vivo() and launchd_estado()["corriendo"]:
        res = {"ok": True, "mensaje": "ya estaba corriendo en %s" % url()}
    elif PLIST.exists():
        ld = launchd_estado()
        if not ld["cargado"]:
            _launchctl("bootstrap", "gui/%d" % os.getuid(), str(PLIST))
        _launchctl("kickstart", "gui/%d/%s" % (os.getuid(), LABEL))
        for _ in range(20):
            if puerto_vivo():
                break
            time.sleep(0.25)
        res = {"ok": puerto_vivo(), "mensaje": ("corriendo en %s" % url()) if puerto_vivo() else "no levantó: revisa var/botonera.log"}
    else:
        res = servicio_instalar(silencioso=True)
    if abrir and res["ok"]:
        subprocess.run(["/usr/bin/open", url()])
    print(json.dumps(res, ensure_ascii=False))
    sys.exit(0 if res["ok"] else 1)


def detener():
    ld = launchd_estado()
    if ld["cargado"]:
        rc, out = _launchctl("bootout", "gui/%d/%s" % (os.getuid(), LABEL))   # con KeepAlive, un kill solo lo reiniciaría
        for _ in range(20):
            if not puerto_vivo():
                break
            time.sleep(0.25)
        ok = not puerto_vivo()
        print(json.dumps({"ok": ok, "mensaje": "servicio detenido (Iniciar lo vuelve a cargar)" if ok else "bootout rc=%s: %s" % (rc, out[:200])}, ensure_ascii=False))
        sys.exit(0 if ok else 1)
    pid = pid_archivo()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(json.dumps({"ok": True, "pid": pid, "mensaje": "detenida (corría en una ventana)"}))
            return
        except OSError as ex:
            print(json.dumps({"ok": False, "mensaje": "no pude detener el pid %s (%s)" % (pid, ex)}, ensure_ascii=False))
            sys.exit(1)
    print(json.dumps({"ok": False, "mensaje": "no estaba corriendo"}))
    sys.exit(1)


def reiniciar():
    if not launchd_estado()["cargado"]:
        return iniciar(abrir=False)
    rc, out = _launchctl("kickstart", "-k", "gui/%d/%s" % (os.getuid(), LABEL))
    time.sleep(1.5)
    ok = puerto_vivo()
    print(json.dumps({"ok": ok, "mensaje": "reiniciado" if ok else "kickstart rc=%s: %s" % (rc, out[:200])}, ensure_ascii=False))
    sys.exit(0 if ok else 1)


def ver_log():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.touch(exist_ok=True)
    r = subprocess.run(["/usr/bin/open", "-a", "Console", str(LOG)], capture_output=True, text=True)
    print(json.dumps({"ok": r.returncode == 0, "mensaje": "abriendo el registro en Consola" if r.returncode == 0 else r.stderr[:200]}, ensure_ascii=False))


def escribir_fichas():
    """Ficha de la propia botonera, con rutas absolutas de este equipo."""
    py, reg = sys.executable, Path(CFG["registro"])
    yo = [py, str(BASE / "botonera.py")]
    escribir_json(reg / "botonera.json", {
        "esquema": "botonera-servicio/1", "id": "botonera", "nombre": "Botonera", "tipo": "servicio",
        "descripcion": "Este panel.", "carpeta": str(BASE),
        "tarjeta": {"cmd": yo + ["tarjeta"], "campo": "tarjeta", "cada_segundos": 30},
        "acciones": {"estado": {"cmd": yo + ["tarjeta"], "salida": "json"},
                     "iniciar": {"cmd": yo + ["iniciar", "--sin-abrir"], "salida": "json"},
                     "reiniciar": {"cmd": yo + ["reiniciar"], "salida": "json"},
                     "detener": {"cmd": yo + ["detener"], "salida": "json", "confirmar": True},
                     "ver_log": {"cmd": yo + ["ver_log"], "salida": "json"},
                     "abrir": {"cmd": ["/usr/bin/open", url()]}},
        "archivos": {"log": str(LOG), "pid": str(VAR / "botonera.pid"), "plist": str(PLIST)},
    })
    print(json.dumps({"ok": True, "registro": str(reg), "fichas": ["botonera"]}, ensure_ascii=False))


def main():
    accion_cli = sys.argv[1] if len(sys.argv) > 1 else "servir"
    if accion_cli == "servir":
        servir("--abrir" in sys.argv)
    elif accion_cli == "tarjeta":
        tarjeta_propia()
    elif accion_cli == "iniciar":
        iniciar(abrir="--sin-abrir" not in sys.argv)
    elif accion_cli == "detener":
        detener()
    elif accion_cli == "reiniciar":
        reiniciar()
    elif accion_cli == "ver_log":
        ver_log()
    elif accion_cli == "servicio":
        sub = sys.argv[2] if len(sys.argv) > 2 else ""
        if sub == "instalar":
            servicio_instalar()
        elif sub == "desinstalar":
            servicio_desinstalar()
        else:
            sys.exit("uso: botonera.py servicio instalar|desinstalar")
    elif accion_cli == "fichas":
        escribir_fichas()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
