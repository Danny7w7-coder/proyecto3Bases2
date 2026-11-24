"""
Corre todas las pruebas de la carpeta tests/ y muestra OK / FALLO por prueba.

Cada archivo tests/test_*.py tiene una lista PRUEBAS con funciones.
Una prueba pasa si termina sin error. Si devuelve un texto, se muestra como detalle.
Falla si lanza una excepción (por ejemplo un assert que no se cumple).

Uso:
    python scripts/correr_pruebas.py               # todas las pruebas
    python scripts/correr_pruebas.py estructura    # solo tests/test_estructura.py
"""
import glob
import importlib
import os
import sys

from comun import RAIZ

# Para poder importar los módulos de tests/ y de scripts/
sys.path.insert(0, os.path.join(RAIZ, "tests"))


def main():
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    archivos = sorted(glob.glob(os.path.join(RAIZ, "tests", "test_*.py")))
    aprobadas = 0
    fallidas = 0

    for ruta in archivos:
        modulo_nombre = os.path.basename(ruta)[:-3]
        if filtro and filtro not in modulo_nombre:
            continue
        modulo = importlib.import_module(modulo_nombre)
        print(f"\n== {modulo_nombre} ==")
        for prueba in modulo.PRUEBAS:
            # La primera línea del docstring es el nombre legible de la prueba
            nombre = (prueba.__doc__ or prueba.__name__).strip().splitlines()[0]
            try:
                detalle = prueba()
                aprobadas += 1
                print(f"  OK     {nombre}" + (f"  ({detalle})" if detalle else ""))
            except Exception as error:
                fallidas += 1
                print(f"  FALLO  {nombre}\n         -> {type(error).__name__}: {error}")

    print(f"\nResultado: {aprobadas} OK, {fallidas} FALLO")
    sys.exit(1 if fallidas else 0)


if __name__ == "__main__":
    main()
