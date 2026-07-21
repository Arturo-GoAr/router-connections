import sys
from pathlib import Path

# Los tests importan `app.*` sin instalar el paquete, así que el directorio
# `backend/` tiene que estar en el path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
