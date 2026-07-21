@echo off
setlocal EnableExtensions
title Router Connections - Dev

REM ===================================================================
REM  Arranca backend (uvicorn --reload) y frontend (vite) en ESTA MISMA
REM  ventana. Al cerrarla, Windows termina todos los procesos que
REM  quedaron colgados de esta consola (backend, npm, node y vite), asi
REM  que no hace falta buscar procesos sueltos en el Administrador de
REM  tareas.
REM
REM  Se lanzan con "start /b", que ejecuta el proceso sin abrir una
REM  ventana nueva: el proceso queda enganchado a la consola actual en
REM  vez de crear la suya propia. Por eso, al cerrar esta ventana,
REM  Windows los mata a todos junto con ella.
REM ===================================================================

cd /d "%~dp0"
set "ROOT=%~dp0"
set "VENV_PY=%ROOT%backend\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo Falta el entorno virtual del backend. Creándolo con:
    echo   cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "%ROOT%frontend\node_modules" (
    echo Faltan las dependencias del frontend. Instálalas con:
    echo   cd frontend ^&^& npm install
    pause
    exit /b 1
)

echo.
echo  ================================================
echo   Router Connections - modo desarrollo
echo  ================================================
echo.
echo  Backend  -^> http://127.0.0.1:8000/docs
echo  Frontend -^> http://localhost:5173
echo.
echo  Cierra esta ventana para detener TODO (backend y frontend).
echo.

start "" /b cmd /c "cd /d "%ROOT%backend" && "%VENV_PY%" -m uvicorn app.main:app --reload"
start "" /b cmd /c "cd /d "%ROOT%frontend" && npm run dev"

REM  Mantiene la ventana abierta y sirve como "raiz" de la consola de la
REM  que cuelgan los dos procesos de arriba.
:loop
timeout /t 3600 /nobreak >nul
goto :loop
