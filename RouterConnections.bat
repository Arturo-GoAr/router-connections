@echo off
setlocal EnableExtensions
title Router Connections

REM ===================================================================
REM  Router Connections - lanzador unico
REM
REM  Hace todo lo necesario para arrancar la aplicacion con un solo
REM  doble clic: pide permisos de administrador, prepara el entorno de
REM  Python la primera vez, compila el frontend si hace falta, abre el
REM  navegador y arranca el servidor.
REM
REM  Se ejecuta como administrador porque es lo unico que permite crear
REM  y borrar reglas del Firewall de Windows. Todo lo demas (escaneo,
REM  UPnP, inventario) funciona igual sin elevacion.
REM ===================================================================

REM --- 1. Elevacion --------------------------------------------------
REM  `fltmc` es un comando que solo se ejecuta con privilegios, asi que
REM  sirve para saber si ya estamos elevados. Si no lo estamos, se
REM  relanza este mismo archivo con UAC y esta instancia termina.
fltmc >nul 2>&1
if errorlevel 1 (
    echo Solicitando permisos de administrador...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b 0
)

cd /d "%~dp0"

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%backend\.venv\Scripts\python.exe"

echo.
echo  ================================================
echo   Router Connections
echo  ================================================
echo.

REM --- 2. Entorno de Python ------------------------------------------
if not exist "%VENV_PY%" (
    call :buscar_python
    if errorlevel 1 goto :sin_python

    echo [1/3] Creando el entorno virtual de Python...
    %BASE_PY% -m venv "%ROOT%backend\.venv"
    if errorlevel 1 goto :fallo
)

REM  Comprobar que las dependencias estan instaladas es mas fiable que
REM  fiarse de que exista la carpeta del entorno virtual.
"%VENV_PY%" -c "import fastapi, uvicorn, sqlmodel, zeroconf, apscheduler" >nul 2>&1
if errorlevel 1 (
    echo [1/3] Instalando dependencias de Python. Esto tarda un poco la primera vez...
    "%VENV_PY%" -m pip install --upgrade pip --quiet
    "%VENV_PY%" -m pip install -r "%ROOT%backend\requirements.txt" --quiet
    if errorlevel 1 goto :fallo
) else (
    echo [1/3] Entorno de Python listo.
)

REM --- 3. Frontend compilado -----------------------------------------
if exist "%ROOT%frontend\dist\index.html" (
    echo [2/3] Interfaz web ya compilada.
    goto :arrancar
)

where npm >nul 2>&1
if errorlevel 1 (
    echo [2/3] AVISO: no se encontro npm, asi que no se puede compilar la interfaz.
    echo       El servidor arrancara igualmente y la API quedara disponible en /docs.
    echo       Instala Node.js desde https://nodejs.org y vuelve a ejecutar este archivo.
    goto :arrancar
)

if not exist "%ROOT%frontend\node_modules" (
    echo [2/3] Instalando dependencias de la interfaz...
    pushd "%ROOT%frontend"
    call npm install --silent
    popd
)

echo [2/3] Compilando la interfaz web...
pushd "%ROOT%frontend"
call npm run build
popd
if not exist "%ROOT%frontend\dist\index.html" (
    echo       AVISO: la compilacion no genero dist\index.html. Se arranca solo la API.
)

REM --- 4. Arranque ---------------------------------------------------
:arrancar
echo [3/3] Arrancando el servidor...
echo.
echo  La aplicacion se abrira en el navegador:  http://127.0.0.1:8000
echo  Documentacion de la API:                  http://127.0.0.1:8000/docs
echo.
echo  Cierra esta ventana o pulsa Ctrl+C para detenerla.
echo.

REM  El navegador se abre en segundo plano tras una pausa, para dar
REM  tiempo a que el servidor este escuchando.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 6; Start-Process 'http://127.0.0.1:8000'"

cd /d "%ROOT%backend"
"%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo  El servidor se ha detenido.
pause
exit /b 0

REM --- Subrutinas ----------------------------------------------------

REM  Busca un Python utilizable. El alias de Microsoft Store que Windows
REM  pone en el PATH no es un Python real, pero falla al pedirle la
REM  version, asi que la comprobacion lo descarta solo.
:buscar_python
set "BASE_PY="
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "BASE_PY=py -3"
    exit /b 0
)
python --version >nul 2>&1
if not errorlevel 1 (
    set "BASE_PY=python"
    exit /b 0
)
exit /b 1

:sin_python
echo.
echo  ERROR: no se encontro Python.
echo.
echo  Instalalo desde https://www.python.org/downloads/ y marca la casilla
echo  "Add Python to PATH" durante la instalacion. Despues vuelve a
echo  ejecutar este archivo.
echo.
pause
exit /b 1

:fallo
echo.
echo  ERROR: la preparacion del entorno fallo. Revisa los mensajes de arriba.
echo.
pause
exit /b 1
