"""
Empaqueta el plugin como .zip instalable en QGIS ("Instalar a partir de ZIP").

Resultado: dist/sigtec.zip, con la carpeta sigtec/ en la raíz del zip (así lo exige QGIS).
Se omiten __pycache__ y archivos .pyc.

Uso: python scripts/empaquetar_plugin.py
"""
import os
import py_compile
import zipfile

from comun import RAIZ

CARPETA_PLUGIN = os.path.join(RAIZ, "plugin", "sigtec")
DESTINO = os.path.join(RAIZ, "dist", "sigtec.zip")
OBLIGATORIOS = ["__init__.py", "metadata.txt", "plugin.py", "icon.png", "config.ini"]


def main():
    # 1. Revisar que estén los archivos que QGIS necesita
    for nombre in OBLIGATORIOS:
        if not os.path.exists(os.path.join(CARPETA_PLUGIN, nombre)):
            raise SystemExit(f"ERROR: falta plugin/sigtec/{nombre}")

    # 2. Revisar que todos los .py compilen (sin errores de sintaxis)
    for nombre in os.listdir(CARPETA_PLUGIN):
        if nombre.endswith(".py"):
            py_compile.compile(os.path.join(CARPETA_PLUGIN, nombre), doraise=True)

    # 3. Armar el zip
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    with zipfile.ZipFile(DESTINO, "w", zipfile.ZIP_DEFLATED) as archivo_zip:
        for carpeta, subcarpetas, archivos in os.walk(CARPETA_PLUGIN):
            subcarpetas[:] = [s for s in subcarpetas if s != "__pycache__"]
            for nombre in sorted(archivos):
                if nombre.endswith(".pyc"):
                    continue
                ruta = os.path.join(carpeta, nombre)
                dentro_del_zip = os.path.join("sigtec", os.path.relpath(ruta, CARPETA_PLUGIN))
                archivo_zip.write(ruta, dentro_del_zip)
                print(f"  + {dentro_del_zip}")
    print(f"Listo: {DESTINO}")


if __name__ == "__main__":
    main()
