@echo off
rem instalar.cmd - Windows (beta): instala la Botonera + OSHealth. Doble clic, o desde una consola:
rem   instalar.cmd              Botonera + OSHealth
rem   instalar.cmd --sin-salud  solo la Botonera
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1" %*
echo.
pause
