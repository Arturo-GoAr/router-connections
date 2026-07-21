# Arranca backend y frontend en ventanas separadas.
#
# Para poder gestionar el Firewall de Windows hay que abrir esta ventana como
# administrador; sin elevación todo lo demás funciona igual.

$root = $PSScriptRoot
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host 'Falta el entorno virtual. Créalo con:' -ForegroundColor Yellow
    Write-Host '  cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt'
    exit 1
}

if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) {
    Write-Host 'Faltan las dependencias del frontend. Instálalas con:' -ForegroundColor Yellow
    Write-Host '  cd frontend; npm install'
    exit 1
}

Write-Host 'Backend  -> http://127.0.0.1:8000/docs' -ForegroundColor Cyan
Write-Host 'Frontend -> http://localhost:5173' -ForegroundColor Cyan

Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$root\backend'; & '$python' -m uvicorn app.main:app --reload"
)

Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$root\frontend'; npm run dev"
)
