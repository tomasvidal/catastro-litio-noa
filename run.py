"""
Abre la app de consulta en el navegador.

    uv run python run.py

Equivale a `uv run streamlit run streamlit_app.py`, pero se puede correr desde cualquier
carpeta. Para cerrarla: Ctrl+C en la terminal.
"""

import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent / "streamlit_app.py"

if __name__ == "__main__":
    try:
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(APP), *sys.argv[1:]],
                       cwd=APP.parent, check=False)
    except KeyboardInterrupt:
        pass
