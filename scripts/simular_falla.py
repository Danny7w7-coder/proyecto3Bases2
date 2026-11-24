"""
Simula la pérdida total de un nodo: apaga el contenedor, lo elimina y BORRA su volumen de datos.
El volumen del WAL archivado (/wal_archive) se conserva: en un sistema real estaría en
otro disco u otro servidor.

Uso: python scripts/simular_falla.py limon
"""
import subprocess
import sys

from comun import NODOS, RAIZ
from restaurar import nombre_volumen


def perder_nodo(nodo):
    volumen = nombre_volumen(nodo, "data")
    subprocess.run(["docker", "compose", "rm", "-s", "-f", nodo], cwd=RAIZ, check=True, capture_output=True)
    print(f"  [{nodo}] contenedor detenido y eliminado")
    subprocess.run(["docker", "volume", "rm", volumen], check=True, capture_output=True)
    print(f"  [{nodo}] volumen de datos {volumen} BORRADO")


if __name__ == "__main__":
    nodo = sys.argv[1] if len(sys.argv) > 1 else ""
    if nodo not in NODOS or nodo == "central":
        sys.exit("uso: python scripts/simular_falla.py <campus>")
    perder_nodo(nodo)
