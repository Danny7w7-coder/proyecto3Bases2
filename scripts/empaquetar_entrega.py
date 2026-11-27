"""
Arma el zip de entrega: ../sig-tec.zip (junto a la carpeta del proyecto).

Incluye: fuentes (SQL, Python, Docker), plugin empaquetado (dist/sigtec.zip),
informe, guion del video, documentación y figuras.
No incluye: backups/ (pesados), .git/, __pycache__/, los zips viejos ni el .env
(cada instalación genera su .env con claves aleatorias a partir de .env.example).

Uso: python scripts/empaquetar_entrega.py
"""
import os
import subprocess
import sys
import zipfile

from comun import RAIZ

DESTINO = os.path.join(os.path.dirname(RAIZ), "sig-tec.zip")
EXCLUIR_CARPETAS = {".git", "backups", "__pycache__", ".vscode", ".venv"}
# Documentos de trabajo del grupo: se quedan en la computadora, no van en la entrega
SOLO_LOCALES = {"docs/DECISIONES.md", "docs/GUION_VIDEO.md", "docs/CHECKLIST_ENUNCIADO.md",
                "pruebas_resultado.txt"}  # este último lo crea la preparación del video


def main():
    """Genera el plugin y arma ../sig-tec.zip con todo lo que se entrega."""
    # El plugin empaquetado tiene que estar al día
    subprocess.run([sys.executable, os.path.join(RAIZ, "scripts", "empaquetar_plugin.py")], check=True,
                   capture_output=True)
    # Si falta alguno de estos archivos, la entrega no está completa
    obligatorios = ["README.md", "docker-compose.yml", ".env.example", "docs/Documentacion_Proyecto3.docx",
                    "dist/sigtec.zip"]
    for archivo in obligatorios:
        if not os.path.exists(os.path.join(RAIZ, archivo)):
            sys.exit(f"ERROR: falta {archivo}")

    # Se recorre toda la carpeta del proyecto y se agrega cada archivo al zip
    total = 0
    with zipfile.ZipFile(DESTINO, "w", zipfile.ZIP_DEFLATED) as salida:
        for carpeta, subcarpetas, archivos in os.walk(RAIZ):
            # No se entra en .git, backups, .venv ni carpetas de caché
            subcarpetas[:] = sorted(s for s in subcarpetas if s not in EXCLUIR_CARPETAS)
            for nombre in sorted(archivos):
                ruta = os.path.join(carpeta, nombre)
                relativa = os.path.relpath(ruta, RAIZ)
                # Se omiten el .env (claves), los documentos locales, los .pyc y otros zip
                if nombre == ".env" or relativa.replace("\\", "/") in SOLO_LOCALES or nombre.endswith(".pyc") or (
                        nombre.endswith(".zip") and relativa != os.path.join("dist", "sigtec.zip")):
                    continue
                # Dentro del zip todo queda bajo la carpeta sig-tec/
                salida.write(ruta, os.path.join("sig-tec", relativa))
                total += 1
    print(f"Listo: {DESTINO}")
    print(f"{total} archivos, {os.path.getsize(DESTINO) / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
