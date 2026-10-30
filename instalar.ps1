# instalar.ps1 — Windows (beta): instala (o actualiza) la Botonera en %USERPROFILE%\dev\botonera y OSHealth en \dev\win_health.
#   powershell -ExecutionPolicy Bypass -File instalar.ps1 [--sin-salud]
# Variables opcionales: BOTONERA_HOME (destino), BOTONERA_PYTHON (python.exe), BOTONERA_PUERTO (8790).
# Se puede repetir para actualizar: conserva config.json y las fichas que tú agregues.
$ErrorActionPreference = "Stop"
$Origen  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Destino = if ($env:BOTONERA_HOME) { $env:BOTONERA_HOME } else { Join-Path $env:USERPROFILE "dev\botonera" }
$Puerto  = if ($env:BOTONERA_PUERTO) { $env:BOTONERA_PUERTO } else { 8790 }
$SinSalud = $args -contains "--sin-salud"

Write-Host "== Botonera: instalación (Windows, beta) =="
Write-Host "   origen : $Origen"
Write-Host "   destino: $Destino"

# ---- Python 3.9+ (sin el alias de la Microsoft Store, que solo abre la tienda)
function Buscar-Python {
    if ($env:BOTONERA_PYTHON -and (Test-Path $env:BOTONERA_PYTHON)) { return $env:BOTONERA_PYTHON }
    foreach ($c in @("py -3", "python3", "python")) {
        try {
            $exe = $c.Split(" ")[0]; $arg = @(); if ($c -like "py *") { $arg = @("-3") }
            $v = & $exe @arg -c "import sys; print(sys.executable) if sys.version_info >= (3,9) else exit(1)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v -and ($v -notlike "*WindowsApps*")) { return $v.Trim() }
        } catch {}
    }
    return $null
}
$Py = Buscar-Python
if (-not $Py) {
    Write-Host "   Python 3.9+ no está instalado. Lo instalo con winget (Python.org, solo para tu usuario)…"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements -h
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
        $Py = Buscar-Python
    }
    if (-not $Py) { Write-Host "ERROR: no pude instalar Python. Instálalo desde https://www.python.org/downloads/windows/ (marca 'Add python.exe to PATH') y vuelve a correr este instalador."; exit 1 }
}
Write-Host "   python : $Py"

# ---- archivos
New-Item -ItemType Directory -Force -Path "$Destino\estados", "$Destino\servicios", "$Destino\var" | Out-Null
Copy-Item "$Origen\botonera\botonera.py", "$Origen\botonera\puertos.py", "$Origen\botonera\pagina.html" -Destination $Destino -Force
Copy-Item "$Origen\botonera\estados\comun.py", "$Origen\botonera\estados\ejemplo_launchd.py" -Destination "$Destino\estados" -Force
Copy-Item "$Origen\README.md" -Destination "$Destino\LEEME.md" -Force
if (-not (Test-Path "$Destino\config.json")) {
    $reg = ($Destino -replace '\\', '\\') + '\\servicios'
    "{`n  `"puerto`": $Puerto,`n  `"registro`": `"$reg`"`n}" | Set-Content -Encoding UTF8 "$Destino\config.json"
}
$Pyw = Join-Path (Split-Path $Py) "pythonw.exe"; if (-not (Test-Path $Pyw)) { $Pyw = $Py }
@"
@echo off
rem Arranca la Botonera como tarea de usuario (si no está corriendo) y abre el navegador.
"$Py" "$Destino\botonera.py" iniciar
"@ | Set-Content -Encoding ASCII "$Destino\iniciar_botonera.cmd"

& $Py "$Destino\botonera.py" fichas | Out-Null
Write-Host "   ficha propia escrita en $Destino\servicios\botonera.json"
$r = & $Py "$Destino\botonera.py" servicio instalar
if ($LASTEXITCODE -eq 0) { Write-Host "   tarea programada 'Botonera' corriendo en http://127.0.0.1:$Puerto/ (arranca sola al iniciar sesión)" }
else { Write-Host "   AVISO: la tarea no levantó ($r); revisa $Destino\var\botonera.log" }

# ---- OSHealth
if (-not $SinSalud) {
    $WH = if ($env:WIN_HEALTH_HOME) { $env:WIN_HEALTH_HOME } else { Join-Path $env:USERPROFILE "dev\win_health" }
    New-Item -ItemType Directory -Force -Path $WH | Out-Null
    Copy-Item "$Origen\win_health\win_health.py", "$Origen\win_health\LEEME.md" -Destination $WH -Force
    Write-Host "== OSHealth (win_health) =="
    $env:BOTONERA_HOME = $Destino
    & $Py "$WH\win_health.py" instalar
}

Write-Host ""
Write-Host "Listo. Abre http://127.0.0.1:$Puerto/ en tu navegador (o doble clic en $Destino\iniciar_botonera.cmd)."
Start-Process "http://127.0.0.1:$Puerto/"
Write-Host "Para sumar tus propios servicios: docs\CONECTAR.md y fichas-ejemplo\."
