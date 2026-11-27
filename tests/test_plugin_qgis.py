"""
Corre tests/qgis/probar_plugin_qgis.py con el Python de QGIS (si QGIS está instalado).

El Python de QGIS se busca así:
  1. variable de entorno QGIS_PYTHON (ruta al ejecutable o .bat)
  2. Windows: C:\\Program Files\\QGIS *\\bin\\python-qgis-ltr.bat o python-qgis.bat
Si no se encuentra, la prueba se marca como OMITIDA (no falla).
"""
import glob
import os
import subprocess

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "tests", "qgis", "probar_plugin_qgis.py")


def python_de_qgis():
    """Ruta del Python de QGIS (variable QGIS_PYTHON o la instalación de Windows), o None si no hay."""
    if os.environ.get("QGIS_PYTHON"):
        return os.environ["QGIS_PYTHON"]
    candidatos = sorted(glob.glob(r"C:\Program Files\QGIS *\bin\python-qgis-ltr.bat")
                        + glob.glob(r"C:\Program Files\QGIS *\bin\python-qgis.bat"))
    return candidatos[-1] if candidatos else None


def prueba_plugin_dentro_de_qgis():
    """Plugin dentro de QGIS: login, 8 capas, estilos, edición propia y ajena (12 pruebas)"""
    python = python_de_qgis()
    if not python:
        return "OMITIDA: no se encontró QGIS (defina QGIS_PYTHON)"
    resultado = subprocess.run([python, SCRIPT], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=600)
    lineas = [l for l in resultado.stdout.splitlines() if l.startswith(("OK", "FALLO", "RESULTADO", "       ->"))]
    fallos = [l for l in lineas if l.startswith(("FALLO", "       ->"))]
    assert resultado.returncode == 0 and not fallos, "\n".join(fallos) or resultado.stderr[-2000:]
    return lineas[-1] if lineas else "sin salida"


PRUEBAS = [prueba_plugin_dentro_de_qgis]
