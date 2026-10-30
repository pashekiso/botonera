#!/usr/bin/env python3
"""
mac_health.py — salud del MacBook para la Botonera (solo biblioteca estándar, macOS, Python 3.9+).

Subcomandos:
  medir        lee el sistema, calcula el semáforo y escribe var/estado.json (lo corre launchd cada hora)
  tarjeta      imprime el JSON con el campo 'tarjeta' que lee la Botonera (rápido: solo lee estado.json)
  preparar     lanza la mantención previa al reinicio en segundo plano (la Botonera vuelve enseguida)
  preparar --ejecutar   corre la mantención en este proceso (lo usa 'preparar')
  reiniciar    pide a macOS reiniciar (las apps con documentos sin guardar pueden detenerlo)
  ver_log      abre var/mantencion.log en Consola
  instalar     escribe el plist de launchd (cada 3600 s), la ficha de la Botonera y, si existe, el espejo para la IA
  desinstalar  quita el plist y la ficha

Semáforo (umbrales por defecto; ajústalos en UMBRAL):
  rojo      swap usado > 4 GB · encendido > 7 días · pageouts creciendo 3 lecturas seguidas ·
            presión de memoria crítica · disco libre < 10 GB
  amarillo  swap > 1.5 GB · encendido > 3 días · presión de memoria en aviso · disco libre < 25 GB ·
            carga por núcleo > 1.5 · límite térmico de CPU < 100 % · > 5 servidores en localhost ·
            ~/Library/Caches > 10 GB · kernel_task > 30 % CPU
"""
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(os.environ.get("MAC_HEALTH_HOME") or Path(__file__).resolve().parent).resolve()
VAR = BASE / "var"
ESTADO = VAR / "estado.json"
HISTORIAL = VAR / "historial.jsonl"
MANTENCION = VAR / "mantencion.json"
LOG_MANT = VAR / "mantencion.log"
HOME = Path.home()
# Carpeta compartida con tu asistente de IA (opcional): si existe, se deja ahí una copia de solo lectura del estado.
COWORK = Path(os.environ.get("COWORK_LOCAL") or HOME / "dev" / "cowork-local") / "mac_health"
BOTONERA = Path(os.environ.get("BOTONERA_HOME") or HOME / "dev" / "botonera")
LABEL = "local.mac-health"
PLIST = HOME / "Library" / "LaunchAgents" / (LABEL + ".plist")
PYTHON = sys.executable
UID = os.getuid()

UMBRAL = {
    "swap_rojo_gb": 4.0, "swap_amarillo_gb": 1.5,
    "uptime_rojo_d": 7, "uptime_amarillo_d": 3,
    "disco_rojo_gb": 10, "disco_amarillo_gb": 25,
    "carga_por_nucleo": 1.5, "listeners": 5, "caches_gb": 10, "kernel_task_cpu": 30,
    "pageouts_delta": 20000,      # páginas por lectura (≈330 MB con páginas de 16 KB)
    "pageouts_lecturas": 3,
}

# Procesos que la mantención considera "de maquetas y pruebas" (se cierran). Se evalúa sobre la línea de comando.
RE_DEV = re.compile(
    r"(uvicorn|gunicorn|hypercorn|flask run|http\.server|streamlit|marimo|jupyter|vite|next dev|webpack|nodemon|"
    r"ts-node|live-server|ngrok|cloudflared|ms-playwright|--headless|Chrome for Testing|chromium|"
    r"--remote-debugging-port|--user-data-dir=.*/dev/)", re.I)
# Nunca se tocan (además del propio proceso): la Botonera, apps instaladas, el sistema, colima/lima y ssh.
# Se evalúa sobre la línea de comando COMPLETA (no la recortada para mostrar).
RE_PROTEGIDO = re.compile(r"(botonera\.py|mac_health\.py|/System/|/usr/libexec/|/usr/sbin/|/Library/Apple/|/Applications/|"
                          r"/Library/Application Support/|limactl|/\.colima/|/\.lima/|(^|/)ssh[: ]|/opt/homebrew/(opt|Cellar)/(colima|lima|docker)|"
                          r"Claude\.app|Terminal\.app|iTerm\.app|Google Chrome\.app|Safari\.app|Arc\.app|Brave Browser\.app|Firefox\.app|Microsoft Edge\.app)", re.I)
APPS_NO_CERRAR = {"Finder", "Terminal", "iTerm2", "Claude", "Google Chrome", "Safari", "Arc", "Brave Browser", "Firefox",
                  "Microsoft Edge", "Vivaldi", "Opera", "Orion", "loginwindow", "Dock", "SystemUIServer", "Control Center",
                  "Notification Center"}


def protegido(cmd):
    """True si el proceso no debe cerrarse. Playwright vive en ~/Library/Caches/ms-playwright y sí se cierra."""
    if "ms-playwright" in cmd:
        return False
    return bool(RE_PROTEGIDO.search(cmd))
CACHES_PROTEGER = {"ms-playwright"}
AVISO_PREPARAR = ("ATENCIÓN, esto va a:\n"
                  "• Cerrar las apps abiertas (salvo Finder, Terminal, Claude y navegadores) y los servidores y procesos de pruebas.\n"
                  "• Vaciar la PAPELERA: lo que esté ahí se borra para siempre. Si guardas cosas en la Papelera, sácalas antes.\n"
                  "• Borrar las cachés de usuario: algunas apps tardarán más en abrir la primera vez y volverán a descargar datos.\n"
                  "• Limpiar temporales, registros antiguos y el estado guardado de ventanas.\n"
                  "Corre en segundo plano (1 a 3 min); el avance se ve en esta tarjeta.")


# --------------------------------------------------------------------------- utilidades
def run(cmd, timeout=15, texto=True):
    """Ejecuta sin shell. Devuelve (rc, stdout+stderr). rc 124 = tiempo agotado, 127 = no existe."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=texto, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "tiempo agotado (%ss)" % timeout
    except FileNotFoundError:
        return 127, "no existe: %s" % cmd[0]
    except Exception as ex:
        return 1, "%s: %s" % (type(ex).__name__, ex)


def sysctl(clave):
    rc, out = run(["/usr/sbin/sysctl", "-n", clave], 5)
    return out.strip() if rc == 0 else ""


def gb(n):
    return round(n / 1024 ** 3, 2)


def leer_json(p, defecto=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def escribir_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def espejo(nombre, obj):
    """Copia de solo lectura para el asistente de IA, solo si la carpeta compartida existe."""
    if not COWORK.parent.is_dir():
        return
    try:
        escribir_json(COWORK / nombre, obj)
    except OSError:
        pass


def duracion(s):
    s = int(max(0, s))
    if s < 3600:
        return "%d min" % (s // 60)
    if s < 172800:
        return "%d h %d min" % (s // 3600, (s % 3600) // 60)
    return "%d días %d h" % (s // 86400, (s % 86400) // 3600)


def hace(s):
    if s is None:
        return "nunca"
    s = int(max(0, s))
    if s < 90:
        return "hace %d s" % s
    if s < 5400:
        return "hace %d min" % (s // 60)
    if s < 172800:
        return "hace %d h" % (s // 3600)
    return "hace %d días" % (s // 86400)


def du_kb(ruta, timeout=25):
    rc, out = run(["/usr/bin/du", "-sk", str(ruta)], timeout)
    m = re.match(r"\s*(\d+)", out or "")
    return int(m.group(1)) if rc in (0, 1) and m else None    # du devuelve 1 si no pudo leer algo


# --------------------------------------------------------------------------- medición
def medir_sistema():
    d = {"ts": time.time(), "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    m = re.search(r"sec = (\d+)", sysctl("kern.boottime"))
    d["boottime"] = int(m.group(1)) if m else None
    d["uptime_s"] = (time.time() - d["boottime"]) if d["boottime"] else None

    sw = sysctl("vm.swapusage")
    def _mb(etq):
        m = re.search(etq + r" = ([\d.]+)([KMG])", sw)
        if not m:
            return 0.0
        v, u = float(m.group(1)), m.group(2)
        return v / 1024 if u == "K" else v if u == "M" else v * 1024
    d["swap_usado_gb"] = round(_mb("used") / 1024, 2)
    d["swap_total_gb"] = round(_mb("total") / 1024, 2)

    nivel = sysctl("kern.memorystatus_vm_pressure_level")
    d["presion_nivel"] = int(nivel) if nivel.isdigit() else None      # 1 normal · 2 aviso · 4 crítica
    d["presion_texto"] = {1: "normal", 2: "aviso", 4: "crítica"}.get(d["presion_nivel"], "desconocida")

    rc, vm = run(["/usr/bin/vm_stat"], 8)
    pag = re.search(r"page size of (\d+)", vm)
    tam = int(pag.group(1)) if pag else 16384
    def _pg(etq):
        m = re.search(r"^" + etq + r":\s+(\d+)", vm, re.M)
        return int(m.group(1)) if m else 0
    d["pagina_bytes"] = tam
    d["pageouts"] = _pg("Pages paged out")
    d["compresor_gb"] = gb(_pg("Pages occupied by compressor") * tam)
    usado = (_pg("Pages active") + _pg("Pages wired down") + _pg("Pages occupied by compressor")) * tam
    d["mem_usada_gb"] = gb(usado)
    mem = sysctl("hw.memsize")
    d["mem_total_gb"] = gb(int(mem)) if mem.isdigit() else None

    m = re.search(r"\{\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)", sysctl("vm.loadavg"))
    d["carga_1m"] = float(m.group(1)) if m else None
    ncpu = sysctl("hw.logicalcpu") or sysctl("hw.ncpu")
    d["nucleos"] = int(ncpu) if ncpu.isdigit() else None
    d["carga_por_nucleo"] = round(d["carga_1m"] / d["nucleos"], 2) if d["carga_1m"] is not None and d["nucleos"] else None

    rc, th = run(["/usr/bin/pmset", "-g", "therm"], 8)
    m = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", th)
    d["limite_termico_cpu"] = int(m.group(1)) if m else None

    rc, ps = run(["/bin/ps", "-Aro", "pid,pcpu,rss,comm"], 10)
    top, kernel = [], 0.0
    for linea in ps.splitlines()[1:]:
        partes = linea.split(None, 3)
        if len(partes) < 4:
            continue
        try:
            pid, cpu, rss = int(partes[0]), float(partes[1]), int(partes[2])
        except ValueError:
            continue
        nombre = os.path.basename(partes[3])
        if nombre == "kernel_task":
            kernel = cpu
        if len(top) < 6 and nombre != "ps":
            top.append({"pid": pid, "cpu": cpu, "mem_mb": rss // 1024, "proceso": nombre})
    d["kernel_task_cpu"] = kernel
    d["top"] = top

    try:
        u = shutil.disk_usage("/System/Volumes/Data")
    except OSError:
        u = shutil.disk_usage("/")
    d["disco_libre_gb"] = gb(u.free)
    d["disco_total_gb"] = gb(u.total)

    kb = du_kb(HOME / "Library" / "Caches")
    d["caches_gb"] = round(kb / 1024 ** 2, 2) if kb is not None else None

    d["listeners"] = listeners()
    d["procesos_dev"] = procesos_dev()
    return d


def listeners():
    """Puertos TCP en escucha del usuario: [{pid, proceso, puerto, comando}]."""
    rc, out = run(["/usr/sbin/lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-u", str(UID), "-Fpcn"], 12)
    res, pid, nombre, vistos = [], None, None, set()
    for l in out.splitlines():
        if l.startswith("p"):
            pid = int(l[1:])
        elif l.startswith("c"):
            nombre = l[1:]
        elif l.startswith("n") and pid:
            m = re.search(r":(\d+)$", l)
            if m and (pid, m.group(1)) not in vistos:
                vistos.add((pid, m.group(1)))
                res.append({"pid": pid, "proceso": nombre, "puerto": int(m.group(1))})
    cmds = comandos({r["pid"] for r in res})
    for r in res:
        completo = cmds.get(r["pid"], "")
        r["comando"] = completo[:160]
        r["protegido"] = protegido(completo)
    return res


def comandos(pids):
    if not pids:
        return {}
    rc, out = run(["/bin/ps", "-o", "pid=,command=", "-p", ",".join(str(p) for p in pids)], 8)
    res = {}
    for l in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(.*)", l)
        if m:
            res[int(m.group(1))] = m.group(2)
    return res


def procesos_dev():
    """Procesos del usuario que parecen servidores de desarrollo, Playwright/Chrome headless, etc."""
    rc, out = run(["/bin/ps", "-U", str(UID), "-o", "pid=,ppid=,etime=,rss=,command="], 10)
    yo = {os.getpid(), os.getppid()}
    res = []
    for l in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(\d+)\s+(\S+)\s+(\d+)\s+(.*)", l)
        if not m:
            continue
        pid, ppid, etime, rss, cmd = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4)), m.group(5)
        if pid in yo or protegido(cmd) or not RE_DEV.search(cmd):
            continue
        res.append({"pid": pid, "ppid": ppid, "tiempo": etime, "mem_mb": rss // 1024, "comando": cmd[:160]})
    return res


def evaluar(d, historial):
    """Semáforo + motivos a partir de la medición y de las lecturas anteriores (mismo arranque)."""
    rojo, amarillo = [], []
    U = UMBRAL
    if d["swap_usado_gb"] > U["swap_rojo_gb"]:
        rojo.append("swap usado %.1f GB (> %.0f GB)" % (d["swap_usado_gb"], U["swap_rojo_gb"]))
    elif d["swap_usado_gb"] > U["swap_amarillo_gb"]:
        amarillo.append("swap usado %.1f GB" % d["swap_usado_gb"])
    dias = (d["uptime_s"] or 0) / 86400
    if dias > U["uptime_rojo_d"]:
        rojo.append("encendido hace %d días (> %d)" % (dias, U["uptime_rojo_d"]))
    elif dias > U["uptime_amarillo_d"]:
        amarillo.append("encendido hace %d días" % dias)
    if d["presion_nivel"] == 4:
        rojo.append("presión de memoria crítica")
    elif d["presion_nivel"] == 2:
        amarillo.append("presión de memoria en aviso")
    if d["disco_libre_gb"] < U["disco_rojo_gb"]:
        rojo.append("disco libre %.0f GB (< %d GB)" % (d["disco_libre_gb"], U["disco_rojo_gb"]))
    elif d["disco_libre_gb"] < U["disco_amarillo_gb"]:
        amarillo.append("disco libre %.0f GB" % d["disco_libre_gb"])
    # pageouts: acumulado desde el arranque; miramos los incrementos entre lecturas consecutivas
    previas = [h for h in historial if h.get("boottime") == d["boottime"]][-U["pageouts_lecturas"]:]
    serie = [h["pageouts"] for h in previas] + [d["pageouts"]]
    deltas = [b - a for a, b in zip(serie, serie[1:])]
    d["pageouts_deltas"] = deltas
    if len(deltas) >= U["pageouts_lecturas"] and all(x > U["pageouts_delta"] for x in deltas):
        rojo.append("memoria paginando a disco en %d lecturas seguidas (+%d MB/h aprox.)"
                    % (len(deltas), deltas[-1] * d["pagina_bytes"] // 1024 ** 2))
    elif deltas and deltas[-1] > U["pageouts_delta"]:
        amarillo.append("paginó a disco en la última hora (+%d MB)" % (deltas[-1] * d["pagina_bytes"] // 1024 ** 2))
    if (d["carga_por_nucleo"] or 0) > U["carga_por_nucleo"]:
        amarillo.append("carga por núcleo %.1f" % d["carga_por_nucleo"])
    if d["limite_termico_cpu"] is not None and d["limite_termico_cpu"] < 100:
        amarillo.append("CPU limitada por temperatura al %d %%" % d["limite_termico_cpu"])
    abiertos = [l for l in d["listeners"] if not l["protegido"]]
    if len(abiertos) > U["listeners"]:
        amarillo.append("%d servidores locales abiertos" % len(abiertos))
    if (d["caches_gb"] or 0) > U["caches_gb"]:
        amarillo.append("~/Library/Caches ocupa %.1f GB" % d["caches_gb"])
    if d["kernel_task_cpu"] > U["kernel_task_cpu"]:
        amarillo.append("kernel_task al %.0f %% de CPU (suele ser control térmico)" % d["kernel_task_cpu"])

    if rojo:
        sem, rec = "rojo", "Conviene reiniciar: " + "; ".join(rojo)
    elif amarillo:
        sem, rec = "amarillo", "Vigilar: " + "; ".join(amarillo)
    else:
        sem, rec = "verde", "Sin señales de degradación"
    d["semaforo"], d["motivos_rojo"], d["motivos_amarillo"], d["recomendacion"] = sem, rojo, amarillo, rec
    return d


def medir():
    VAR.mkdir(parents=True, exist_ok=True)
    historial = []
    try:
        for l in HISTORIAL.read_text(encoding="utf-8").splitlines():
            try:
                historial.append(json.loads(l))
            except ValueError:
                pass
    except OSError:
        pass
    d = evaluar(medir_sistema(), historial)
    escribir_json(ESTADO, d)
    espejo("estado.json", d)
    compacto = {k: d.get(k) for k in ("ts", "fecha", "boottime", "semaforo", "swap_usado_gb", "pageouts", "presion_nivel",
                                       "mem_usada_gb", "carga_1m", "disco_libre_gb", "caches_gb", "kernel_task_cpu")}
    compacto["listeners"] = len(d["listeners"])
    historial.append(compacto)
    HISTORIAL.write_text("\n".join(json.dumps(h, ensure_ascii=False) for h in historial[-200:]) + "\n", encoding="utf-8")
    espejo("historial.json", historial[-48:])
    return d


# --------------------------------------------------------------------------- tarjeta para la Botonera
def tarjeta():
    d = leer_json(ESTADO) or {}
    mant = leer_json(MANTENCION) or {}
    edad = (time.time() - d["ts"]) if d.get("ts") else None
    datos, atencion = [], []
    if not d:
        sem, sub = "gris", "Sin lecturas todavía: pulsa Medir ahora o espera al agente de launchd"
    else:
        sem, sub = d["semaforo"], d["recomendacion"]
        if edad is not None and edad > 2 * 3600:
            atencion.append("La última lectura es %s: el agente launchd %s puede no estar cargado" % (hace(edad), LABEL))
            if sem == "verde":
                sem = "amarillo"
        datos += [
            {"etiqueta": "Última lectura", "valor": hace(edad)},
            {"etiqueta": "Encendido hace", "valor": duracion(d.get("uptime_s") or 0)},
            {"etiqueta": "Memoria", "valor": "%s de %s GB usados · compresor %s GB · presión %s" % (
                d.get("mem_usada_gb"), d.get("mem_total_gb"), d.get("compresor_gb"), d.get("presion_texto"))},
            {"etiqueta": "Swap", "valor": "%s de %s GB" % (d.get("swap_usado_gb"), d.get("swap_total_gb"))},
            {"etiqueta": "Carga / térmico", "valor": "%s por núcleo · %s" % (
                d.get("carga_por_nucleo"), ("CPU al %s %%" % d["limite_termico_cpu"]) if d.get("limite_termico_cpu") is not None else "sin límite térmico reportado")},
            {"etiqueta": "Disco libre", "valor": "%s GB · Caches %s GB" % (d.get("disco_libre_gb"), d.get("caches_gb"))},
            {"etiqueta": "Servidores locales", "valor": "%d (%d de maquetas/pruebas)" % (
                len(d.get("listeners", [])), len([l for l in d.get("listeners", []) if not l.get("protegido")]))},
        ]
        if d.get("procesos_dev"):
            datos.append({"etiqueta": "Procesos de maquetas", "valor": ", ".join(
                sorted({os.path.basename(p["comando"].split()[0]) for p in d["procesos_dev"] if p["comando"]})[:8])})
        if d.get("top"):
            t = d["top"][0]
            datos.append({"etiqueta": "Mayor consumo", "valor": "%s (%.0f %% CPU, %d MB)" % (t["proceso"], t["cpu"], t["mem_mb"])})
        for m in d.get("motivos_rojo", []) + d.get("motivos_amarillo", []):
            atencion.append(m)

    if mant.get("estado") == "en_curso":
        sem = "amarillo"
        sub = "Mantención en curso: paso %s/%s · %s" % (mant.get("paso_n"), mant.get("total"), mant.get("paso"))
        if mant.get("inicio") and time.time() - mant["inicio"] > 1200:
            atencion.append("La mantención lleva más de 20 min: revisa el registro; puede haber una app esperando confirmación")
    elif mant.get("estado") == "listo" and mant.get("fin"):
        reiniciado = d.get("boottime") and d["boottime"] > mant["fin"]
        if not reiniciado and time.time() - mant["fin"] < 6 * 3600:
            sub = "Listo para reiniciar (mantención %s, liberó %s MB)" % (hace(time.time() - mant["fin"]), mant.get("liberado_mb", "?"))
            for p in mant.get("pendientes", []):
                atencion.append(p)
        datos.append({"etiqueta": "Última mantención", "valor": "%s · %d pasos, %d con problemas" % (
            mant.get("fecha_fin", "?"), len(mant.get("pasos", [])), len([p for p in mant.get("pasos", []) if not p.get("ok")]))})
    elif mant.get("estado") == "error":
        atencion.append("La última mantención terminó con error: " + str(mant.get("error", ""))[:200])

    print(json.dumps({"servicio": "mac_health", "corriendo": True, "crudo": {"estado": d, "mantencion": mant},
                      "tarjeta": {"semaforo": sem, "titulo": "OSHealth", "subtitulo": sub, "datos": datos,
                                  "atencion": atencion}}, ensure_ascii=False))


# --------------------------------------------------------------------------- mantención previa al reinicio
class Mantencion:
    PASOS = [
        ("Detener colima / Docker", "detener_docker"),
        ("Cerrar servidores locales de maquetas", "cerrar_servidores"),
        ("Cerrar procesos de pruebas (Playwright, dev servers)", "cerrar_procesos_dev"),
        ("Cerrar aplicaciones abiertas", "cerrar_apps"),
        ("Limpiar cachés de desarrollo (brew, npm, pip, uv)", "caches_dev"),
        ("Vaciar ~/Library/Caches", "caches_usuario"),
        ("Limpiar temporales del usuario", "temporales"),
        ("Borrar registros antiguos (> 7 días)", "logs_viejos"),
        ("Vaciar la Papelera", "papelera"),
        ("Borrar estado guardado de ventanas", "estado_ventanas"),
        ("Desactivar reapertura de ventanas al iniciar", "no_reabrir"),
        ("Vaciar caché DNS", "dns"),
        ("Revisar ítems de inicio de sesión", "login_items"),
    ]

    def __init__(self):
        VAR.mkdir(parents=True, exist_ok=True)
        self.log = open(LOG_MANT, "a", encoding="utf-8")
        self.estado = {"estado": "en_curso", "inicio": time.time(), "fecha_inicio": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "pasos": [], "pendientes": [], "total": len(self.PASOS), "paso_n": 0, "paso": ""}
        self.liberado_kb = 0
        self.escribir()

    def escribir(self):
        escribir_json(MANTENCION, self.estado)
        espejo("mantencion.json", self.estado)

    def nota(self, texto):
        self.log.write("%s  %s\n" % (datetime.now().strftime("%H:%M:%S"), texto))
        self.log.flush()

    def correr(self):
        self.nota("==== mantención previa al reinicio ====")
        for i, (titulo, metodo) in enumerate(self.PASOS, 1):
            self.estado.update(paso_n=i, paso=titulo)
            self.escribir()
            self.nota("[%d/%d] %s" % (i, len(self.PASOS), titulo))
            t0 = time.time()
            try:
                detalle = getattr(self, metodo)() or "ok"
                ok = True
            except Exception as ex:
                detalle, ok = "%s: %s" % (type(ex).__name__, ex), False
            self.nota("      %s %s (%.1f s)" % ("✓" if ok else "✗", detalle, time.time() - t0))
            self.estado["pasos"].append({"nombre": titulo, "ok": ok, "detalle": str(detalle)[:400], "segundos": round(time.time() - t0, 1)})
        self.estado.update(estado="listo", fin=time.time(), fecha_fin=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           liberado_mb=self.liberado_kb // 1024, paso="")
        self.escribir()
        self.nota("==== lista: liberó %d MB. Pendientes: %s ====" % (self.estado["liberado_mb"], "; ".join(self.estado["pendientes"]) or "ninguno"))
        try:
            medir()
        except Exception as ex:
            self.nota("medir tras la mantención falló: %s" % ex)

    # --- pasos -------------------------------------------------------------
    def _matar(self, pids, que):
        pids = [p for p in pids if p not in (os.getpid(), os.getppid())]
        if not pids:
            return "nada que cerrar"
        for p in pids:
            try:
                os.kill(p, 15)
            except ProcessLookupError:
                pass
            except PermissionError:
                self.nota("      sin permiso para cerrar pid %d" % p)
        time.sleep(3)
        vivos = []
        for p in pids:
            try:
                os.kill(p, 0)
                vivos.append(p)
            except (ProcessLookupError, PermissionError):
                pass
        for p in vivos:
            try:
                os.kill(p, 9)
            except (ProcessLookupError, PermissionError):
                pass
        return "%d %s cerrados (%d forzados)" % (len(pids), que, len(vivos))

    def cerrar_servidores(self):
        ls = [l for l in listeners() if not l["protegido"]]
        for l in ls:
            self.nota("      :%d %s — %s" % (l["puerto"], l["proceso"], l["comando"][:100]))
        return self._matar(sorted({l["pid"] for l in ls}), "servidores")

    def cerrar_procesos_dev(self):
        ps = procesos_dev()
        for p in ps:
            self.nota("      pid %d (%s) %s" % (p["pid"], p["tiempo"], p["comando"][:100]))
        return self._matar([p["pid"] for p in ps], "procesos")

    def detener_docker(self):
        partes = []
        colima = shutil.which("colima") or ("/opt/homebrew/bin/colima" if os.path.exists("/opt/homebrew/bin/colima") else None)
        if colima:
            rc, out = run([colima, "status"], 20)
            if rc == 0:
                rc, out = run([colima, "stop"], 120)
                partes.append("colima stop rc=%d" % rc)
            else:
                partes.append("colima no estaba corriendo")
        for app in ("Docker Desktop", "Docker"):
            rc, out = run(["/usr/bin/pgrep", "-x", app], 5)
            if rc == 0:
                run(["/usr/bin/osascript", "-e", 'tell application "%s" to quit' % app], 30)
                partes.append("%s: quit" % app)
        return "; ".join(partes) or "sin Docker ni colima"

    def cerrar_apps(self):
        rc, out = run(["/usr/bin/osascript", "-e",
                       'tell application "System Events" to get name of every application process whose background only is false'], 15)
        if rc != 0:
            raise RuntimeError("System Events no respondió (¿falta permiso de Automatización para Terminal/Python?): " + out.strip()[:150])
        apps = [a.strip() for a in out.strip().split(",") if a.strip()]
        cerradas, quedaron = [], []
        for app in apps:
            if app in APPS_NO_CERRAR:
                continue
            run(["/usr/bin/osascript", "-e", 'tell application "%s" to quit' % app.replace('"', '\\"')], 20)
            cerradas.append(app)
        time.sleep(4)
        rc, out = run(["/usr/bin/osascript", "-e",
                       'tell application "System Events" to get name of every application process whose background only is false'], 15)
        vivas = {a.strip() for a in out.strip().split(",")} if rc == 0 else set()
        quedaron = [a for a in cerradas if a in vivas]
        for a in quedaron:
            self.estado["pendientes"].append("%s sigue abierta: probablemente espera que guardes o confirmes algo" % a)
        return "%d apps cerradas; quedaron: %s" % (len(cerradas) - len(quedaron), ", ".join(quedaron) or "ninguna")

    def _borrar_contenido(self, carpeta, proteger=(), mas_viejo_que_s=None):
        carpeta = Path(carpeta)
        if not carpeta.is_dir():
            return 0, 0
        antes = du_kb(carpeta, 90) or 0
        n = 0
        ahora = time.time()
        try:
            hijos = list(carpeta.iterdir())
        except PermissionError:
            raise
        for hijo in hijos:
            if hijo.name in proteger:
                continue
            try:
                if mas_viejo_que_s is not None and ahora - hijo.lstat().st_mtime < mas_viejo_que_s:
                    continue
                if hijo.is_dir() and not hijo.is_symlink():
                    shutil.rmtree(hijo, ignore_errors=True)
                else:
                    hijo.unlink(missing_ok=True)
                n += 1
            except OSError as ex:
                self.nota("      no pude borrar %s: %s" % (hijo, ex))
        despues = du_kb(carpeta, 90) or 0
        self.liberado_kb += max(0, antes - despues)
        return n, max(0, antes - despues) // 1024

    def caches_dev(self):
        partes = []
        brew = shutil.which("brew") or "/opt/homebrew/bin/brew"
        if os.path.exists(brew):
            rc, out = run([brew, "cleanup", "-s", "--prune=all"], 180)
            partes.append("brew cleanup rc=%d" % rc)
        npm = shutil.which("npm")
        if npm:
            rc, out = run([npm, "cache", "clean", "--force"], 120)
            partes.append("npm cache clean rc=%d" % rc)
        rc, out = run([PYTHON, "-m", "pip", "cache", "purge"], 60)
        partes.append("pip cache purge rc=%d" % rc)
        uv = shutil.which("uv")
        if uv:
            rc, out = run([uv, "cache", "clean"], 60)
            partes.append("uv cache clean rc=%d" % rc)
        derived = HOME / "Library" / "Developer" / "Xcode" / "DerivedData"
        if derived.is_dir():
            n, mb = self._borrar_contenido(derived)
            partes.append("DerivedData %d MB" % mb)
        return "; ".join(partes)

    def caches_usuario(self):
        n, mb = self._borrar_contenido(HOME / "Library" / "Caches", proteger=CACHES_PROTEGER)
        return "%d entradas, %d MB (protegido: %s)" % (n, mb, ", ".join(sorted(CACHES_PROTEGER)))

    def temporales(self):
        rc, tmp = run(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], 5)
        tmp = tmp.strip()
        if rc != 0 or not tmp or not os.path.isdir(tmp):
            return "sin carpeta temporal"
        n, mb = self._borrar_contenido(tmp, mas_viejo_que_s=3600)
        return "%d entradas (> 1 h), %d MB en %s" % (n, mb, tmp)

    def logs_viejos(self):
        n, mb = self._borrar_contenido(HOME / "Library" / "Logs", mas_viejo_que_s=7 * 86400)
        return "%d entradas, %d MB" % (n, mb)

    def papelera(self):
        try:
            n, mb = self._borrar_contenido(HOME / ".Trash")
            return "%d elementos, %d MB" % (n, mb)
        except PermissionError:
            pass
        # Sin Acceso total al disco, ~/.Trash está vedado para Python: se lo pedimos a Finder, que sí puede.
        rc, out = run(["/usr/bin/osascript", "-e", 'tell application "Finder" to empty trash'], 60)
        if rc != 0:
            raise RuntimeError("Finder no pudo vaciar la Papelera: " + out.strip()[:150])
        return "vaciada por Finder (Python no tiene Acceso total al disco)"

    def estado_ventanas(self):
        n, mb = self._borrar_contenido(HOME / "Library" / "Saved Application State")
        return "%d apps sin estado guardado" % n

    def no_reabrir(self):
        rc1, _ = run(["/usr/bin/defaults", "write", "com.apple.loginwindow", "TALLogoutSavesState", "-bool", "false"], 10)
        rc2, _ = run(["/usr/bin/defaults", "write", "-g", "NSQuitAlwaysKeepsWindows", "-bool", "false"], 10)
        return "loginwindow rc=%d, NSQuitAlwaysKeepsWindows rc=%d" % (rc1, rc2)

    def dns(self):
        rc, out = run(["/usr/bin/dscacheutil", "-flushcache"], 10)
        return "dscacheutil rc=%d (mDNSResponder requiere sudo; el reinicio lo renueva igual)" % rc

    def login_items(self):
        rc, out = run(["/usr/bin/osascript", "-e", 'tell application "System Events" to get the name of every login item'], 15)
        items = [a.strip() for a in out.strip().split(",") if a.strip()] if rc == 0 else []
        agentes = sorted(p.name for p in (HOME / "Library" / "LaunchAgents").glob("*.plist")) if (HOME / "Library" / "LaunchAgents").is_dir() else []
        self.estado["login_items"] = items
        self.estado["launch_agents"] = agentes
        return "%d ítems de inicio (%s); %d LaunchAgents de usuario" % (len(items), ", ".join(items)[:200] or "ninguno", len(agentes))


def preparar(ejecutar):
    if ejecutar:
        Mantencion().correr()
        return
    mant = leer_json(MANTENCION) or {}
    if mant.get("estado") == "en_curso" and time.time() - mant.get("inicio", 0) < 1800:
        print(json.dumps({"ok": False, "mensaje": "ya hay una mantención en curso (paso %s/%s)" % (mant.get("paso_n"), mant.get("total"))}))
        return
    VAR.mkdir(parents=True, exist_ok=True)
    with open(LOG_MANT, "a", encoding="utf-8") as f:
        subprocess.Popen([PYTHON, str(Path(__file__).resolve()), "preparar", "--ejecutar"], stdout=f, stderr=f,
                         stdin=subprocess.DEVNULL, start_new_session=True, cwd=str(BASE))
    print(json.dumps({"ok": True, "mensaje": "mantención iniciada en segundo plano; el avance se ve en la tarjeta y en Ver registro"},
                     ensure_ascii=False))


def reiniciar():
    mant = leer_json(MANTENCION) or {}
    if mant.get("estado") == "en_curso":
        print(json.dumps({"ok": False, "mensaje": "la mantención aún está en curso; espera a que termine"}))
        sys.exit(1)
    run(["/usr/bin/defaults", "write", "com.apple.loginwindow", "TALLogoutSavesState", "-bool", "false"], 10)
    rc, out = run(["/usr/bin/osascript", "-e", 'tell application "System Events" to restart'], 30)
    print(json.dumps({"ok": rc == 0, "mensaje": "reinicio solicitado a macOS" if rc == 0 else "macOS no aceptó el reinicio: " + out.strip()[:200]},
                     ensure_ascii=False))
    sys.exit(rc)


def ver_log():
    LOG_MANT.touch(exist_ok=True)
    rc, out = run(["/usr/bin/open", "-a", "Console", str(LOG_MANT)], 10)
    print(json.dumps({"ok": rc == 0, "mensaje": "abriendo el registro en Consola" if rc == 0 else out.strip()[:200]}, ensure_ascii=False))


# --------------------------------------------------------------------------- instalación
def ficha():
    yo = [PYTHON, str(Path(__file__).resolve())]
    return {
        "esquema": "botonera-servicio/1",
        "id": "mac_health",
        "nombre": "OSHealth",
        "tipo": "monitor",
        "descripcion": "Mide cada hora memoria, swap, presión, carga, disco y servidores locales; recomienda reiniciar y prepara el equipo para que vuelva limpio.",
        "carpeta": str(BASE),
        "documentacion": str(BASE / "LEEME.md"),
        "tarjeta": {"cmd": yo + ["tarjeta"], "campo": "tarjeta", "cada_segundos": 20},
        "acciones": {
            "estado": {"cmd": yo + ["tarjeta"], "salida": "json"},
            "medir_ahora": {"cmd": yo + ["medir", "--json"], "salida": "json", "nota": "lectura inmediata; tarda unos segundos (du de Caches)"},
            "preparar_reinicio": {"cmd": yo + ["preparar"], "salida": "json", "confirmar": True,
                                  "aviso": AVISO_PREPARAR,
                                  "nota": "cierra servidores, procesos de pruebas, Docker y apps; limpia cachés, temporales, papelera y estado de ventanas"},
            "reiniciar_ahora": {"cmd": yo + ["reiniciar"], "salida": "json", "confirmar": True,
                                "aviso": "Se reiniciará el Mac ahora. Si alguna app tiene cambios sin guardar, macOS la dejará abierta y el reinicio se cancela."},
            "ver_log": {"cmd": yo + ["ver_log"], "salida": "json"},
        },
        "archivos": {"estado": str(ESTADO), "historial": str(HISTORIAL), "mantencion": str(MANTENCION), "log": str(LOG_MANT),
                     "espejo_cowork": str(COWORK), "plist": str(PLIST)},
    }


def registro_botonera():
    cfg = leer_json(BOTONERA / "config.json") or {}
    return Path(cfg.get("registro") or BOTONERA / "servicios")


def instalar():
    VAR.mkdir(parents=True, exist_ok=True)
    if COWORK.parent.is_dir():
        COWORK.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    pl = {
        "Label": LABEL,
        "ProgramArguments": [PYTHON, str(Path(__file__).resolve()), "medir"],
        "StartInterval": 3600,
        "RunAtLoad": True,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "Nice": 10,
        "StandardOutPath": str(VAR / "launchd.log"),
        "StandardErrorPath": str(VAR / "launchd.log"),
        "WorkingDirectory": str(BASE),
    }
    with open(PLIST, "wb") as f:
        plistlib.dump(pl, f)
    run(["/bin/launchctl", "bootout", "gui/%d/%s" % (UID, LABEL)], 15)
    rc, out = run(["/bin/launchctl", "bootstrap", "gui/%d" % UID, str(PLIST)], 20)
    reg = registro_botonera()
    reg.mkdir(parents=True, exist_ok=True)
    escribir_json(reg / "mac_health.json", ficha())
    print("plist:    %s (%s)" % (PLIST, "cargado en launchd" if rc == 0 else "bootstrap rc=%d: %s" % (rc, out.strip()[:200])))
    print("ficha:    %s" % (reg / "mac_health.json"))
    print("espejo:   %s" % (COWORK if COWORK.parent.is_dir() else "no (no existe %s)" % COWORK.parent))
    print("midiendo por primera vez…")
    d = medir()
    print("semáforo: %s — %s" % (d["semaforo"], d["recomendacion"]))


def desinstalar():
    run(["/bin/launchctl", "bootout", "gui/%d/%s" % (UID, LABEL)], 15)
    for p in (PLIST, registro_botonera() / "mac_health.json"):
        try:
            p.unlink()
            print("borrado", p)
        except OSError:
            pass


def main():
    accion = sys.argv[1] if len(sys.argv) > 1 else "tarjeta"
    if accion == "medir":
        d = medir()
        if "--json" in sys.argv:
            print(json.dumps({"ok": True, "mensaje": "%s — %s" % (d["semaforo"], d["recomendacion"]), "semaforo": d["semaforo"]}, ensure_ascii=False))
        else:
            print("%s  %s  %s" % (d["fecha"], d["semaforo"].upper(), d["recomendacion"]))
    elif accion == "tarjeta":
        tarjeta()
    elif accion == "preparar":
        preparar("--ejecutar" in sys.argv)
    elif accion == "reiniciar":
        reiniciar()
    elif accion == "ver_log":
        ver_log()
    elif accion == "instalar":
        instalar()
    elif accion == "desinstalar":
        desinstalar()
    else:
        sys.exit("acción desconocida: %s (medir | tarjeta | preparar | reiniciar | ver_log | instalar | desinstalar)" % accion)


if __name__ == "__main__":
    main()
