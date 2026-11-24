"""
Levanta los 6 nodos de SIG-TEC y ejecuta los scripts SQL en orden.

Uso:
    python scripts/init_all.py           # levanta y aplica los SQL (se puede repetir)
    python scripts/init_all.py --reset   # BORRA todo (contenedores y volúmenes) y empieza de cero

Los SQL se ejecutan por orden de nombre:
    sql/central/*.sql  -> en el nodo central
    sql/campus/*.sql   -> en cada uno de los 5 campus

Dentro de los SQL se pueden usar estas marcas, que se reemplazan antes de ejecutar:
    {{SRID}}       -> SRID institucional (del .env)
    {{CAMPUS_ID}}  -> número del campus (1 a 5)
    {{CAMPUS}}     -> nombre del esquema del campus (cartago, san_jose, ...)
Todos los SQL deben ser idempotentes (IF NOT EXISTS, CREATE OR REPLACE, etc.).
"""
import glob
import os
import subprocess
import sys

from comun import CAMPUS, NODOS, RAIZ, SRID, conectar, esperar_nodo


def docker_compose(*argumentos):
    """Ejecuta 'docker compose ...' en la carpeta del proyecto y se detiene si falla."""
    comando = ["docker", "compose", *argumentos]
    print("  >", " ".join(comando))
    resultado = subprocess.run(comando, cwd=RAIZ)
    if resultado.returncode != 0:
        sys.exit("ERROR: falló el comando de docker compose")


def ejecutar_carpeta(nodo, carpeta, campus_id=None, campus=None):
    """Ejecuta en el nodo todos los .sql de la carpeta, en orden alfabético."""
    archivos = sorted(glob.glob(os.path.join(RAIZ, "sql", carpeta, "*.sql")))
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    for ruta in archivos:
        with open(ruta, encoding="utf-8") as archivo:
            sql = archivo.read()
        # Reemplazar las marcas por los valores reales
        sql = sql.replace("{{SRID}}", str(SRID))
        if campus_id is not None:
            sql = sql.replace("{{CAMPUS_ID}}", str(campus_id))
            sql = sql.replace("{{CAMPUS}}", campus)
        print(f"  [{nodo}] {carpeta}/{os.path.basename(ruta)}")
        cursor.execute(sql)
    conexion.close()


def main():
    reset = "--reset" in sys.argv

    print("1. Docker")
    if reset:
        print("  --reset: se borran contenedores y volúmenes")
        docker_compose("down", "-v", "--remove-orphans")
    docker_compose("up", "-d", "--build")

    print("2. Esperando a que los nodos respondan")
    for nodo in NODOS:
        if not esperar_nodo(nodo):
            sys.exit(f"ERROR: el nodo {nodo} no respondió a tiempo")
        print(f"  {nodo}: listo")

    print("3. Scripts SQL")
    ejecutar_carpeta("central", "central")
    for campus_id, nombre in CAMPUS:
        ejecutar_carpeta(nombre, "campus", campus_id, nombre)

    print("Listo. Para ver el estado: python scripts/estado_nodos.py")


if __name__ == "__main__":
    main()
