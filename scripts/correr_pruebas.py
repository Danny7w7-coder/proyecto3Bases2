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

from comun import RAIZ, revisar_servidores_de_esta_carpeta

# Para poder importar los módulos de tests/ y de scripts/
sys.path.insert(0, os.path.join(RAIZ, "tests"))


def main():
    """Revisa que los servidores sean de esta carpeta, ejecuta cada tests/test_*.py
    y muestra OK o FALLO por prueba."""
    # Antes de empezar: Docker encendido y servidores de esta carpeta
    problema = revisar_servidores_de_esta_carpeta()
    if problema:
        print(f"\nNo se pueden correr las pruebas.\n  {problema}\n")
        sys.exit(1)

    # Filtro opcional: "python scripts/correr_pruebas.py vistas" corre solo test_vistas.py
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
        # Cada archivo de pruebas tiene una lista PRUEBAS con sus funciones, en orden
        for prueba in modulo.PRUEBAS:
            # La primera línea del docstring es el nombre legible de la prueba
            nombre = (prueba.__doc__ or prueba.__name__).strip().splitlines()[0]
            # Una prueba pasa si termina sin error. Si devuelve texto, se muestra como detalle
            try:
                detalle = prueba()
                aprobadas += 1
                print(f"  OK     {nombre}" + (f"  ({detalle})" if detalle else ""))
            except Exception as error:
                fallidas += 1
                print(f"  FALLO  {nombre}\n         -> {type(error).__name__}: {error}")

    # Código de salida 1 si algo falló (sirve para usarlo desde otros scripts)
    print(f"\nResultado: {aprobadas} OK, {fallidas} FALLO")
    sys.exit(1 if fallidas else 0)


if __name__ == "__main__":
    main()
