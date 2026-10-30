#!/usr/bin/env python3
"""
win_health.py — OSHealth para Windows (beta): salud del equipo para la Botonera. Solo biblioteca estándar, Python 3.9+.

Subcomandos (iguales a mac_health.py):
  medir        lee el sistema (PowerShell/CIM, netstat), calcula el semáforo y escribe var\\estado.json (tarea horaria)
  tarjeta      imprime el JSON con el campo 'tarjeta' que lee la Botonera (rápido: solo lee estado.json)
  preparar     lanza la mantención previa al reinicio en segundo plano
  preparar --ejecutar   corre la mantención en este proceso
  reiniciar    pide a Windows reiniciar (sin forzar: una app con cambios sin guardar puede detenerlo)
  ver_log      abre var\\mantencion.log
  instalar     crea la tarea programada OSHealth (cada hora) y la ficha de la Botonera
  desinstalar  quita la tarea y la ficha

Semáforo (umbrales por defecto; ajústalos en UMBRAL):
  rojo      archivo de paginación usado > 4 GB · encendido > 7 días · memoria libre < 5 % · disco libre < 10 GB ·
            paginando a disco en 3 lecturas seguidas
  amarillo  paginación > 1.5 GB · encendido > 3 días · memoria libre < 12 % · disco < 25 GB · CPU > 85 % ·
            > 5 servidores locales · temporales y cachés > 10 GB
Nota: con "inicio rápido" de Windows, apagar no reinicia el contador de encendido; solo Reiniciar lo hace.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

WIN = sys.platform == "win32"
SUBPROC = {"creationflags": subprocess.CREATE_NO_WINDOW} if WIN else {}
BASE = Path(os.environ.get("WIN_HEALTH_HOME") or Path(__file__).resolve().parent).resolve()
VAR = BASE / "var"
ESTADO, HISTORIAL, MANTENCION, LOG_MANT = VAR / "estado.json", VAR / "historial.jsonl", VAR / "mantencion.json", VAR / "mantencion.log"
HOME = Path.home()
LOCAL = Path(os.environ.get("LOCALAPPDATA") or HOME / "AppData" / "Local")
COWORK = Path(os.environ.get("COWORK_LOCAL") or HOME / "dev" / "cowork-local") / "mac_health"   # mismo nombre que en Mac: la skill lo lee igual
BOTONERA = Path(os.environ.get("BOTONERA_HOME") or HOME / "dev" / "botonera")
TAREA = "OSHealth"
PYTHON = sys.executable

UMBRAL = {
    "pf_rojo_gb": 4.0, "pf_amarillo_gb": 1.5,
    "uptime_rojo_d": 7, "uptime_amarillo_d": 3,
    "libre_rojo_pct": 5, "libre_amarillo_pct": 12,
    "disco_rojo_gb": 10, "disco_amarillo_gb": 25,
    "cpu_pct": 85, "listeners": 5, "caches_gb": 10,
    "pageouts_seg": 50, "pageouts_lecturas": 3,
    "calentamiento_s": 600,
}

RE_DEV = re.compile(r"(uvicorn|gunicorn|hypercorn|flask run|http\.server|streamlit|marimo|jupyter|vite|next dev|webpack|nodemon|"
                    r"ts-node|live-server|ngrok|cloudflared|ms-playwright|--headless|chrome-headless|--remote-debugging-port)", re.I)
RE_PROTEGIDO = re.compile(r"(botonera\.py|win_health\.py|\\Windows\\|\\Program Files|\\WindowsApps\\|\\Microsoft\\|\\Docker\\|wsl|vmmem|svchost|\\AppData\\Local\\Programs\\|"
                          r"\\Claude\\|chrome\.exe|msedge\.exe|firefox\.exe|brave\.exe|opera\.exe|vivaldi\.exe|WindowsTerminal|cmd\.exe|powershell|pwsh)", re.I)
APPS_NO_CERRAR = {"explorer", "WindowsTerminal", "cmd", "powershell", "pwsh", "conhost", "Claude", "chrome", "msedge", "firefox",
                  "brave", "opera", "vivaldi", "python", "pythonw", "ApplicationFrameHost", "TextInputHost", "SystemSettings",
                  "ShellExperienceHost", "StartMenuExperienceHost", "SearchHost", "LockApp", "Widgets", "msrdc", "mstsc"}
AVISO_PREPARAR = ("ATENCIÓN, esto va a:\n"
                  "• Cerrar las apps abiertas (salvo Explorador, Terminal, Claude y navegadores), Docker Desktop/WSL y los servidores y procesos de pruebas.\n"
                  "• Vaciar la PAPELERA DE RECICLAJE: lo que esté ahí se borra para siempre. Si guardas cosas ahí, sácalas antes.\n"
                  "• Borrar temporales y cachés de usuario: algunas apps tardarán más en abrir la primera vez.\n"
                  "• Desactivar la reapertura de apps al iniciar sesión y vaciar la caché DNS.\n"
                  "Corre en segundo plano (1 a 3 min); el avance se ve en esta tarjeta.")


# --------------------------------------------------------------------------- utilidades
def run(cmd, timeout=15, encoding=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding=encoding, errors="replace", **SUBPROC)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "tiempo agotado (%ss)" % timeout
    except FileNotFoundError:
        return 127, "no existe: %s" % cmd[0]
    except Exception as ex:
        return 1, "%s: %s" % (type(ex).__name__, ex)


def ps(script, timeout=40):
    """Ejecuta PowerShell y devuelve (rc, stdout)."""
    script = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; " + script
    rc, out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout, encoding="utf-8")
    return rc, out


def ps_json(script, timeout=40, defecto=None):
    rc, out = ps(script + " | ConvertTo-Json -Compress -Depth 3", timeout)
    try:
        return json.loads(out.strip()) if out.strip() else defecto
    except ValueError:
        return defecto


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


def tamano_kb(carpeta, tope_s=40):
    """Tamaño de una carpeta en KB recorriéndola (con tope de tiempo)."""
    total, t0 = 0, time.time()
    for raiz, dirs, archivos in os.walk(carpeta, onerror=lambda e: None):
        for a in archivos:
            try:
                total += os.lstat(os.path.join(raiz, a)).st_size
            except OSError:
                pass
        if time.time() - t0 > tope_s:
            break
    return total // 1024


def carpetas_cache():
    return [p for p in (Path(os.environ.get("TEMP", LOCAL / "Temp")), LOCAL / "Temp", LOCAL / "pip" / "Cache", LOCAL / "npm-cache",
                        LOCAL / "CrashDumps", LOCAL / "Microsoft" / "Windows" / "WER", LOCAL / "D3DSCache", LOCAL / "NVIDIA" / "DXCache",
                        LOCAL / "uv" / "cache") if p.is_dir()]


# --------------------------------------------------------------------------- medición
def listeners():
    rc, out = run(["netstat", "-ano", "-p", "tcp"], 15)
    rc6, out6 = run(["netstat", "-ano", "-p", "tcpv6"], 15)
    res, vistos = [], set()
    for l in (out + out6).splitlines():
        partes = l.split()
        if len(partes) < 5 or partes[0].upper() != "TCP" or partes[3].upper() != "LISTENING":
            continue
        host, _, puerto = partes[1].rpartition(":")
        if puerto.isdigit() and partes[4].isdigit() and (partes[4], puerto) not in vistos:
            vistos.add((partes[4], puerto))
            res.append({"pid": int(partes[4]), "puerto": int(puerto)})
    procs = procesos()
    for r in res:
        p = procs.get(r["pid"]) or {}
        r["proceso"] = p.get("nombre") or "sistema"
        r["comando"] = (p.get("linea") or "")[:160]
        r["protegido"] = (not p) or protegido(p.get("linea") or "", p.get("exe") or "")
    return res


_procs = None


def procesos():
    """{pid: {nombre, exe, linea, creado}} de los procesos del usuario (Win32_Process)."""
    global _procs
    if _procs is None:
        datos = ps_json("Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath,CommandLine,"
                        "@{n='Creado';e={$_.CreationDate.ToString('yyyy-MM-ddTHH:mm:ss')}}", 60, []) or []
        if isinstance(datos, dict):
            datos = [datos]
        _procs = {}
        for d in datos:
            try:
                _procs[int(d["ProcessId"])] = {"nombre": d.get("Name") or "", "exe": d.get("ExecutablePath") or "",
                                               "linea": d.get("CommandLine") or "", "creado": d.get("Creado")}
            except (KeyError, TypeError, ValueError):
                pass
    return _procs


RE_HOME = re.compile(re.escape(str(HOME)) + r"\\(?!AppData\\)", re.I)     # un script bajo el perfil del usuario = desarrollo


def protegido(linea, exe=""):
    linea = linea or ""
    if "ms-playwright" in linea.lower():
        return False
    if RE_PROTEGIDO.search(linea) and not re.search(r"botonera\.py|win_health\.py|\\Claude\\|chrome\.exe|msedge\.exe|firefox\.exe|brave\.exe|WindowsTerminal|cmd\.exe|powershell|pwsh|wsl|vmmem|svchost", linea, re.I) \
            and RE_HOME.search(linea):
        return False                              # p. ej. node.exe (Program Files) corriendo ~\dev\app\vite.js
    return bool(RE_PROTEGIDO.search(linea) or RE_PROTEGIDO.search(exe or ""))


def procesos_dev():
    yo = {os.getpid(), os.getppid()}
    res = []
    for pid, p in procesos().items():
        if pid in yo or not p["linea"] or protegido(p["linea"], p["exe"]) or not RE_DEV.search(p["linea"]):
            continue
        res.append({"pid": pid, "proceso": p["nombre"], "comando": p["linea"][:160]})
    return res


def medir_sistema():
    d = {"ts": time.time(), "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    sistema = ps_json(
        "$os=Get-CimInstance Win32_OperatingSystem; $pf=Get-CimInstance Win32_PageFileUsage; $cpu=Get-CimInstance Win32_Processor; "
        "$mem=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory; "
        "[pscustomobject]@{total_kb=$os.TotalVisibleMemorySize; libre_kb=$os.FreePhysicalMemory; "
        "boot=$os.LastBootUpTime.ToString('yyyy-MM-ddTHH:mm:ss'); "
        "pf_usado_mb=($pf|Measure-Object CurrentUsage -Sum).Sum; pf_total_mb=($pf|Measure-Object AllocatedBaseSize -Sum).Sum; "
        "cpu_pct=($cpu|Measure-Object LoadPercentage -Average).Average; nucleos=($cpu|Measure-Object NumberOfLogicalProcessors -Sum).Sum; "
        "pages_out=$mem.PagesOutputPersec; commit_mb=[int]($mem.CommittedBytes/1MB)}", 60, {}) or {}
    try:
        boot = datetime.fromisoformat(sistema.get("boot"))
        d["boottime"] = boot.timestamp()
        d["uptime_s"] = time.time() - d["boottime"]
    except (TypeError, ValueError):
        d["boottime"], d["uptime_s"] = None, None
    total_kb, libre_kb = sistema.get("total_kb") or 0, sistema.get("libre_kb") or 0
    d["mem_total_gb"], d["mem_usada_gb"] = round(total_kb / 1024 ** 2, 2), round((total_kb - libre_kb) / 1024 ** 2, 2)
    d["mem_libre_pct"] = round(100 * libre_kb / total_kb, 1) if total_kb else None
    d["pf_usado_gb"], d["pf_total_gb"] = round((sistema.get("pf_usado_mb") or 0) / 1024, 2), round((sistema.get("pf_total_mb") or 0) / 1024, 2)
    d["cpu_pct"], d["nucleos"] = sistema.get("cpu_pct"), sistema.get("nucleos")
    d["pageouts_seg"] = sistema.get("pages_out") or 0
    d["commit_gb"] = round((sistema.get("commit_mb") or 0) / 1024, 2)
    top = ps_json("Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object {$_.Name -notin @('_Total','Idle')} | "
                  "Sort-Object PercentProcessorTime -Descending | Select-Object -First 6 Name,IDProcess,PercentProcessorTime,"
                  "@{n='mem_mb';e={[int]($_.WorkingSetPrivate/1MB)}}", 40, []) or []
    if isinstance(top, dict):
        top = [top]
    n = d["nucleos"] or 1
    d["top"] = [{"proceso": t.get("Name"), "pid": t.get("IDProcess"), "cpu": round((t.get("PercentProcessorTime") or 0) / n, 1),
                 "mem_mb": t.get("mem_mb") or 0} for t in top]
    try:
        u = shutil.disk_usage(str(HOME.anchor))
        d["disco_libre_gb"], d["disco_total_gb"] = gb(u.free), gb(u.total)
    except OSError:
        d["disco_libre_gb"] = d["disco_total_gb"] = None
    d["caches_gb"] = round(sum(tamano_kb(p) for p in carpetas_cache()) / 1024 ** 2, 2)
    d["listeners"] = listeners()
    d["procesos_dev"] = procesos_dev()
    return d


def evaluar(d, historial):
    rojo, amarillo, U = [], [], UMBRAL
    if d["pf_usado_gb"] > U["pf_rojo_gb"]:
        rojo.append("archivo de paginación %.1f GB en uso (> %.0f GB)" % (d["pf_usado_gb"], U["pf_rojo_gb"]))
    elif d["pf_usado_gb"] > U["pf_amarillo_gb"]:
        amarillo.append("archivo de paginación %.1f GB en uso" % d["pf_usado_gb"])
    dias = (d["uptime_s"] or 0) / 86400
    if dias > U["uptime_rojo_d"]:
        rojo.append("encendido hace %d días (> %d)" % (dias, U["uptime_rojo_d"]))
    elif dias > U["uptime_amarillo_d"]:
        amarillo.append("encendido hace %d días" % dias)
    if d["mem_libre_pct"] is not None:
        if d["mem_libre_pct"] < U["libre_rojo_pct"]:
            rojo.append("memoria libre %.0f %% (< %d %%)" % (d["mem_libre_pct"], U["libre_rojo_pct"]))
        elif d["mem_libre_pct"] < U["libre_amarillo_pct"]:
            amarillo.append("memoria libre %.0f %%" % d["mem_libre_pct"])
    if d["disco_libre_gb"] is not None:
        if d["disco_libre_gb"] < U["disco_rojo_gb"]:
            rojo.append("disco libre %.0f GB (< %d GB)" % (d["disco_libre_gb"], U["disco_rojo_gb"]))
        elif d["disco_libre_gb"] < U["disco_amarillo_gb"]:
            amarillo.append("disco libre %.0f GB" % d["disco_libre_gb"])
    previas = [h.get("pageouts_seg", 0) for h in historial if h.get("boottime") == d["boottime"]][-(U["pageouts_lecturas"] - 1):]
    serie = previas + [d["pageouts_seg"]]
    if len(serie) >= U["pageouts_lecturas"] and all(x > U["pageouts_seg"] for x in serie):
        rojo.append("paginando a disco en %d lecturas seguidas (%d pág/s)" % (len(serie), d["pageouts_seg"]))
    elif d["pageouts_seg"] > U["pageouts_seg"]:
        amarillo.append("paginando a disco ahora (%d pág/s)" % d["pageouts_seg"])
    d["calentando"] = (d["uptime_s"] or 0) < U["calentamiento_s"]
    if not d["calentando"] and (d["cpu_pct"] or 0) > U["cpu_pct"]:
        amarillo.append("CPU al %.0f %%" % d["cpu_pct"])
    abiertos = [l for l in d["listeners"] if not l["protegido"]]
    if len(abiertos) > U["listeners"]:
        amarillo.append("%d servidores locales abiertos" % len(abiertos))
    if (d["caches_gb"] or 0) > U["caches_gb"]:
        amarillo.append("temporales y cachés ocupan %.1f GB" % d["caches_gb"])
    if rojo:
        sem, rec = "rojo", "Conviene reiniciar: " + "; ".join(rojo)
    elif amarillo:
        sem, rec = "amarillo", "Vigilar: " + "; ".join(amarillo)
    elif d["calentando"]:
        sem, rec = "gris", "Esperando uptime: recién encendido (%s); la CPU se evalúa a los %d min" % (duracion(d["uptime_s"] or 0), U["calentamiento_s"] // 60)
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
    compacto = {k: d.get(k) for k in ("ts", "fecha", "boottime", "semaforo", "pf_usado_gb", "pageouts_seg", "mem_libre_pct",
                                       "mem_usada_gb", "cpu_pct", "disco_libre_gb", "caches_gb")}
    compacto["listeners"] = len(d["listeners"])
    historial.append(compacto)
    HISTORIAL.write_text("\n".join(json.dumps(h, ensure_ascii=False) for h in historial[-200:]) + "\n", encoding="utf-8")
    espejo("historial.json", historial[-48:])
    return d


# --------------------------------------------------------------------------- tarjeta
def tarjeta():
    d = leer_json(ESTADO) or {}
    mant = leer_json(MANTENCION) or {}
    edad = (time.time() - d["ts"]) if d.get("ts") else None
    datos, atencion = [], []
    if not d:
        sem, sub = "gris", "Sin lecturas todavía: pulsa Medir ahora o espera a la tarea programada"
    else:
        sem, sub = d["semaforo"], d["recomendacion"]
        if edad is not None and edad > 2 * 3600:
            atencion.append("La última lectura es %s: la tarea programada %s puede no estar activa" % (hace(edad), TAREA))
            if sem == "verde":
                sem = "amarillo"
        datos += [
            {"etiqueta": "Última lectura", "valor": hace(edad)},
            {"etiqueta": "Encendido hace", "valor": duracion(d.get("uptime_s") or 0)},
            {"etiqueta": "Memoria", "valor": "%s de %s GB usados · libre %s %% · comprometida %s GB" % (
                d.get("mem_usada_gb"), d.get("mem_total_gb"), d.get("mem_libre_pct"), d.get("commit_gb"))},
            {"etiqueta": "Paginación", "valor": "%s de %s GB" % (d.get("pf_usado_gb"), d.get("pf_total_gb"))},
            {"etiqueta": "CPU", "valor": "%s %% (%s núcleos)" % (d.get("cpu_pct"), d.get("nucleos"))},
            {"etiqueta": "Disco libre", "valor": "%s GB · temporales y cachés %s GB" % (d.get("disco_libre_gb"), d.get("caches_gb"))},
            {"etiqueta": "Servidores locales", "valor": "%d (%d de maquetas/pruebas)" % (
                len(d.get("listeners", [])), len([l for l in d.get("listeners", []) if not l.get("protegido")]))},
        ]
        if d.get("procesos_dev"):
            datos.append({"etiqueta": "Procesos de maquetas", "valor": ", ".join(sorted({p["proceso"] for p in d["procesos_dev"]})[:8])})
        if d.get("top"):
            t = d["top"][0]
            datos.append({"etiqueta": "Mayor consumo", "valor": "%s (%s %% CPU, %s MB)" % (t["proceso"], t["cpu"], t["mem_mb"])})
        atencion += d.get("motivos_rojo", []) + d.get("motivos_amarillo", [])
    progreso = None
    deshabilitar = {"reiniciar_ahora": "primero pulsa Preparar reinicio: deja el equipo limpio antes de reiniciar"}
    if mant.get("estado") == "en_curso":
        sem = "amarillo"
        sub = "Mantención en curso: paso %s/%s · %s" % (mant.get("paso_n"), mant.get("total"), mant.get("paso"))
        progreso = {"paso": mant.get("paso_n"), "total": mant.get("total"), "texto": mant.get("paso") or "iniciando…",
                    "desde": hace(time.time() - mant["inicio"]) if mant.get("inicio") else None}
        deshabilitar = {"preparar_reinicio": "ya hay una mantención en curso", "reiniciar_ahora": "se habilita cuando termine la mantención",
                        "medir_ahora": "espera a que termine la mantención"}
        if mant.get("inicio") and time.time() - mant["inicio"] > 1200:
            atencion.append("La mantención lleva más de 20 min: revisa el registro; puede haber una app esperando confirmación")
    elif mant.get("estado") == "listo" and mant.get("fin"):
        reiniciado = d.get("boottime") and d["boottime"] > mant["fin"]
        if not reiniciado and time.time() - mant["fin"] < 6 * 3600:
            sub = "Listo para reiniciar (mantención %s, liberó %s MB)" % (hace(time.time() - mant["fin"]), mant.get("liberado_mb", "?"))
            deshabilitar = {}
            atencion += mant.get("pendientes", [])
        datos.append({"etiqueta": "Última mantención", "valor": "%s · %d pasos, %d con problemas" % (
            mant.get("fecha_fin", "?"), len(mant.get("pasos", [])), len([p for p in mant.get("pasos", []) if not p.get("ok")]))})
    elif mant.get("estado") == "error":
        atencion.append("La última mantención terminó con error: " + str(mant.get("error", ""))[:200])
    print(json.dumps({"servicio": "mac_health", "corriendo": True, "crudo": {"estado": d, "mantencion": mant},
                      "tarjeta": {"semaforo": sem, "titulo": "OSHealth", "subtitulo": sub, "datos": datos, "atencion": atencion,
                                  "progreso": progreso, "deshabilitar": deshabilitar}}, ensure_ascii=False))


# --------------------------------------------------------------------------- mantención
class Mantencion:
    PASOS = [
        ("Detener Docker Desktop y WSL", "detener_docker"),
        ("Cerrar servidores locales de maquetas", "cerrar_servidores"),
        ("Cerrar procesos de pruebas (Playwright, dev servers)", "cerrar_procesos_dev"),
        ("Cerrar aplicaciones abiertas", "cerrar_apps"),
        ("Limpiar cachés de desarrollo (npm, pip, uv)", "caches_dev"),
        ("Vaciar temporales y cachés de usuario", "caches_usuario"),
        ("Vaciar la Papelera de reciclaje", "papelera"),
        ("Desactivar reapertura de apps al iniciar sesión", "no_reabrir"),
        ("Vaciar caché DNS", "dns"),
        ("Revisar programas de inicio", "inicio"),
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
        self.nota("==== mantención previa al reinicio (Windows) ====")
        for i, (titulo, metodo) in enumerate(self.PASOS, 1):
            self.estado.update(paso_n=i, paso=titulo)
            self.escribir()
            self.nota("[%d/%d] %s" % (i, len(self.PASOS), titulo))
            t0 = time.time()
            try:
                detalle, ok = getattr(self, metodo)() or "ok", True
            except Exception as ex:
                detalle, ok = "%s: %s" % (type(ex).__name__, ex), False
            self.nota("      %s %s (%.1f s)" % ("OK" if ok else "FALLO", detalle, time.time() - t0))
            self.estado["pasos"].append({"nombre": titulo, "ok": ok, "detalle": str(detalle)[:400], "segundos": round(time.time() - t0, 1)})
        self.estado.update(estado="listo", fin=time.time(), fecha_fin=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           liberado_mb=self.liberado_kb // 1024, paso="")
        self.escribir()
        self.nota("==== lista: liberó %d MB. Pendientes: %s ====" % (self.estado["liberado_mb"], "; ".join(self.estado["pendientes"]) or "ninguno"))
        try:
            global _procs
            _procs = None
            medir()
        except Exception as ex:
            self.nota("medir tras la mantención falló: %s" % ex)

    def _matar(self, pids, que):
        pids = [p for p in pids if p not in (os.getpid(), os.getppid())]
        if not pids:
            return "nada que cerrar"
        for p in pids:
            run(["taskkill", "/PID", str(p), "/T"], 15)
        time.sleep(3)
        global _procs
        _procs = None
        vivos = [p for p in pids if p in procesos()]
        for p in vivos:
            run(["taskkill", "/PID", str(p), "/T", "/F"], 15)
        _procs = None
        return "%d %s cerrados (%d forzados)" % (len(pids), que, len(vivos))

    def detener_docker(self):
        partes = []
        rc, out = run(["tasklist", "/FI", "IMAGENAME eq Docker Desktop.exe", "/NH"], 10)
        if "Docker Desktop" in out:
            ps("Get-Process 'Docker Desktop','com.docker.backend' -ErrorAction SilentlyContinue | Stop-Process -Force", 60)
            partes.append("Docker Desktop cerrado")
        if shutil.which("wsl"):
            rc, out = run(["wsl", "--list", "--running"], 20)
            if rc == 0 and len(out.strip().splitlines()) > 1:
                run(["wsl", "--shutdown"], 60)
                partes.append("WSL apagado")
        return "; ".join(partes) or "sin Docker ni WSL corriendo"

    def cerrar_servidores(self):
        ls = [l for l in listeners() if not l["protegido"]]
        for l in ls:
            self.nota("      :%d %s — %s" % (l["puerto"], l["proceso"], l["comando"][:100]))
        return self._matar(sorted({l["pid"] for l in ls}), "servidores")

    def cerrar_procesos_dev(self):
        pr = procesos_dev()
        for p in pr:
            self.nota("      pid %d %s" % (p["pid"], p["comando"][:100]))
        return self._matar([p["pid"] for p in pr], "procesos")

    def cerrar_apps(self):
        excl = ",".join("'%s'" % a for a in APPS_NO_CERRAR)
        datos = ps_json("Get-Process | Where-Object {$_.MainWindowHandle -ne 0 -and $_.ProcessName -notin @(%s)} | "
                        "ForEach-Object { $null = $_.CloseMainWindow(); $_.ProcessName } | Select-Object -Unique" % excl, 40, []) or []
        cerradas = datos if isinstance(datos, list) else [datos]
        time.sleep(5)
        vivas = ps_json("Get-Process | Where-Object {$_.MainWindowHandle -ne 0} | Select-Object -ExpandProperty ProcessName -Unique", 30, []) or []
        vivas = set(vivas if isinstance(vivas, list) else [vivas])
        quedaron = [a for a in cerradas if a in vivas]
        for a in quedaron:
            self.estado["pendientes"].append("%s sigue abierta: probablemente espera que guardes o confirmes algo" % a)
        return "%d apps cerradas; quedaron: %s" % (len(cerradas) - len(quedaron), ", ".join(quedaron) or "ninguna")

    def _borrar_contenido(self, carpeta, mas_viejo_que_s=None):
        carpeta = Path(carpeta)
        if not carpeta.is_dir():
            return 0, 0
        antes, n, ahora = tamano_kb(carpeta, 60), 0, time.time()
        for hijo in carpeta.iterdir():
            try:
                if mas_viejo_que_s is not None and ahora - hijo.lstat().st_mtime < mas_viejo_que_s:
                    continue
                if hijo.is_dir() and not hijo.is_symlink():
                    shutil.rmtree(hijo, ignore_errors=True)
                else:
                    hijo.unlink(missing_ok=True)
                n += 1
            except OSError:
                pass                              # archivos en uso: Windows los protege
        despues = tamano_kb(carpeta, 60)
        self.liberado_kb += max(0, antes - despues)
        return n, max(0, antes - despues) // 1024

    def caches_dev(self):
        partes = []
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if npm:
            rc, _ = run([npm, "cache", "clean", "--force"], 120)
            partes.append("npm cache clean rc=%d" % rc)
        rc, _ = run([PYTHON, "-m", "pip", "cache", "purge"], 60)
        partes.append("pip cache purge rc=%d" % rc)
        uv = shutil.which("uv")
        if uv:
            rc, _ = run([uv, "cache", "clean"], 60)
            partes.append("uv cache clean rc=%d" % rc)
        return "; ".join(partes)

    def caches_usuario(self):
        total_n, total_mb = 0, 0
        for p in carpetas_cache():
            if p.name.lower() in ("cache", "npm-cache") and p.parent.name.lower() in ("pip", "local"):
                continue                          # ya los vació el paso anterior
            n, mb = self._borrar_contenido(p, mas_viejo_que_s=3600 if p.name.lower() == "temp" else None)
            total_n, total_mb = total_n + n, total_mb + mb
        return "%d entradas, %d MB" % (total_n, total_mb)

    def papelera(self):
        rc, out = ps("Clear-RecycleBin -Force -ErrorAction Stop; 'ok'", 60)
        if rc != 0 or "ok" not in out:
            raise RuntimeError(out.strip()[:150] or "Clear-RecycleBin falló")
        return "vaciada"

    def no_reabrir(self):
        rc, out = run(["reg", "add", r"HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon", "/v", "RestartApps", "/t", "REG_DWORD", "/d", "0", "/f"], 10)
        return "RestartApps=0 rc=%d" % rc

    def dns(self):
        rc, _ = run(["ipconfig", "/flushdns"], 15)
        return "ipconfig /flushdns rc=%d" % rc

    def inicio(self):
        items = ps_json("Get-CimInstance Win32_StartupCommand | Select-Object -ExpandProperty Name", 30, []) or []
        items = items if isinstance(items, list) else [items]
        self.estado["login_items"] = items
        return "%d programas de inicio (%s)" % (len(items), ", ".join(items)[:200] or "ninguno")


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
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS} if WIN else {"start_new_session": True}
        subprocess.Popen([PYTHON, str(Path(__file__).resolve()), "preparar", "--ejecutar"], stdout=f, stderr=f,
                         stdin=subprocess.DEVNULL, cwd=str(BASE), **flags)
    t0 = time.time()
    while time.time() - t0 < 3:
        m = leer_json(MANTENCION) or {}
        if m.get("estado") == "en_curso" and m.get("inicio", 0) >= t0 - 1:
            break
        time.sleep(0.2)
    print(json.dumps({"ok": True, "mensaje": "mantención iniciada; el avance se ve en la tarjeta y en Ver registro"}, ensure_ascii=False))


def reiniciar():
    mant = leer_json(MANTENCION) or {}
    if mant.get("estado") == "en_curso":
        print(json.dumps({"ok": False, "mensaje": "la mantención aún está en curso; espera a que termine"}))
        sys.exit(1)
    # /t 0 sin /f: una app con cambios sin guardar puede detener el reinicio (Windows lo muestra en pantalla).
    rc, out = run(["shutdown", "/r", "/t", "0", "/c", "Botonera: reinicio tras la mantencion"], 20)
    print(json.dumps({"ok": rc == 0, "mensaje": "reinicio solicitado a Windows" if rc == 0 else "Windows no aceptó el reinicio: " + out.strip()[:200]}, ensure_ascii=False))
    sys.exit(rc)


def ver_log():
    LOG_MANT.touch(exist_ok=True)
    os.startfile(str(LOG_MANT))
    print(json.dumps({"ok": True, "mensaje": "abriendo el registro"}))


# --------------------------------------------------------------------------- instalación
def ficha():
    yo = [PYTHON, str(Path(__file__).resolve())]
    return {
        "esquema": "botonera-servicio/1", "id": "mac_health", "nombre": "OSHealth", "tipo": "monitor",
        "descripcion": "Mide cada hora memoria, paginación, CPU, disco y servidores locales; recomienda reiniciar y prepara el equipo para que vuelva limpio.",
        "carpeta": str(BASE), "documentacion": str(BASE / "LEEME.md"),
        "tarjeta": {"cmd": yo + ["tarjeta"], "campo": "tarjeta", "cada_segundos": 5},
        "acciones": {
            "estado": {"cmd": yo + ["tarjeta"], "salida": "json"},
            "medir_ahora": {"cmd": yo + ["medir", "--json"], "salida": "json", "nota": "lectura inmediata; tarda unos segundos"},
            "preparar_reinicio": {"cmd": yo + ["preparar"], "salida": "json", "confirmar": True, "aviso": AVISO_PREPARAR},
            "reiniciar_ahora": {"cmd": yo + ["reiniciar"], "salida": "json", "confirmar": True,
                                "aviso": "Se reiniciará el equipo ahora. Si alguna app tiene cambios sin guardar, Windows lo detendrá y te lo mostrará."},
            "ver_log": {"cmd": yo + ["ver_log"], "salida": "json"},
        },
        "archivos": {"estado": str(ESTADO), "historial": str(HISTORIAL), "mantencion": str(MANTENCION), "log": str(LOG_MANT), "tarea": TAREA},
    }


def registro_botonera():
    cfg = leer_json(BOTONERA / "config.json") or {}
    return Path(cfg.get("registro") or BOTONERA / "servicios")


def pythonw():
    c = Path(PYTHON).with_name("pythonw.exe")
    return str(c if c.exists() else PYTHON)


def instalar():
    VAR.mkdir(parents=True, exist_ok=True)
    if COWORK.parent.is_dir():
        COWORK.mkdir(parents=True, exist_ok=True)
    tr = '"%s" "%s" medir' % (pythonw(), Path(__file__).resolve())
    rc, out = run(["schtasks", "/Create", "/F", "/TN", TAREA, "/SC", "HOURLY", "/RL", "LIMITED", "/TR", tr], 20)
    reg = registro_botonera()
    reg.mkdir(parents=True, exist_ok=True)
    escribir_json(reg / "mac_health.json", ficha())
    print("tarea:    %s (%s)" % (TAREA, "creada, cada hora" if rc == 0 else "schtasks rc=%d: %s" % (rc, out.strip()[:200])))
    print("ficha:    %s" % (reg / "mac_health.json"))
    print("midiendo por primera vez…")
    d = medir()
    print("semáforo: %s — %s" % (d["semaforo"], d["recomendacion"]))


def desinstalar():
    run(["schtasks", "/Delete", "/F", "/TN", TAREA], 15)
    try:
        (registro_botonera() / "mac_health.json").unlink()
        print("ficha borrada")
    except OSError:
        pass
    print("tarea %s eliminada" % TAREA)


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
