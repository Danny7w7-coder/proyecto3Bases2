"""
Levanta los 6 nodos de SIG-TEC y ejecuta los scripts SQL en orden.

Uso:
    python scripts/init_all.py              # levanta, aplica los SQL y carga datos de ejemplo
    python scripts/init_all.py --reset      # BORRA todo (contenedores y volúmenes) y empieza de cero
    python scripts/init_all.py --sin-datos  # no carga los datos de ejemplo

Carpetas de SQL:
    sql/central/  -> solo en el nodo central
    sql/campus/   -> en cada uno de los 5 campus
    sql/comun/    -> en los 6 nodos
En cada nodo se juntan los archivos de su carpeta + los de comun/ y se ejecutan
ordenados por nombre (por eso empiezan con un número: 00_, 05_, 10_, ...).

Si el nombre del archivo tiene "por_esquema", se ejecuta 5 veces en el nodo:
una por cada esquema de campus (cartago, san_jose, san_carlos, alajuela, limon).

Marcas que se reemplazan antes de ejecutar:
    {{CLAVE}}       -> cualquier valor del .env: {{SRID}}, {{REPL_USER}}, {{PORT_CARTAGO}}, ...
    {{NODO}}        -> nombre del nodo (central, cartago, ...)
    {{CAMPUS_ID}}   -> campus del nodo (1 a 5). En el central vale NULL
    {{ESQUEMA}}     -> (solo en archivos por_esquema) nombre del esquema
    {{ESQUEMA_ID}}  -> (solo en archivos por_esquema) campus dueño de ese esquema
Todos los SQL deben ser idempotentes (IF NOT EXISTS, CREATE OR REPLACE, etc.).
Si se cambia la estructura de una tabla ya creada, hay que usar --reset.
"""
import glob
import os
import subprocess
import sys

from comun import CAMPUS, ENV, NODOS, RAIZ, conectar, esperar_nodo


def docker_compose(*argumentos):
    """Ejecuta 'docker compose ...' en la carpeta del proyecto y se detiene si falla."""
    comando = ["docker", "compose", *argumentos]
    print("  >", " ".join(comando))
    resultado = subprocess.run(comando, cwd=RAIZ)
    if resultado.returncode != 0:
        sys.exit("ERROR: falló el comando de docker compose")


def hay_instalacion_de_otra_carpeta():
    """Hay una sola instalación de SIG-TEC por computadora (contenedores y volúmenes con nombre fijo).
    Si la que existe se creó desde OTRA carpeta del proyecto, tiene otras contraseñas (otro .env).
    En ese caso se quitan sus contenedores y la red, y se devuelve True para empezar de cero."""
    resultado = subprocess.run(["docker", "ps", "-a", "--filter", "name=sigtec_", "--format", "{{.Names}}"],
                               capture_output=True, text=True)
    ajenos = []
    for nombre in resultado.stdout.split():
        carpeta = subprocess.run(
            ["docker", "inspect", "-f", '{{index .Config.Labels "com.docker.compose.project.working_dir"}}', nombre],
            capture_output=True, text=True).stdout.strip()
        if os.path.normcase(os.path.normpath(carpeta)) != os.path.normcase(os.path.normpath(RAIZ)):
            ajenos.append(nombre)
    if ajenos:
        print("  Había una instalación de SIG-TEC creada desde otra carpeta (con otras contraseñas).")
        print("  Como solo puede haber una por computadora, se reemplaza: se empieza de cero.")
        subprocess.run(["docker", "rm", "-f", *ajenos], capture_output=True)
        subprocess.run(["docker", "network", "rm", "sigtec_red"], capture_output=True)
    return bool(ajenos)


def archivos_del_nodo(nodo):
    """Lista ordenada de los .sql que le tocan al nodo (su carpeta + comun)."""
    carpeta = "central" if nodo == "central" else "campus"
    archivos = glob.glob(os.path.join(RAIZ, "sql", carpeta, "*.sql"))
    archivos += glob.glob(os.path.join(RAIZ, "sql", "comun", "*.sql"))
    return sorted(archivos, key=os.path.basename)


def ejecutar_sql_nodo(nodo):
    """Ejecuta en el nodo todos sus archivos SQL, reemplazando las marcas."""
    campus_id = NODOS[nodo]["campus_id"]
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    for ruta in archivos_del_nodo(nodo):
        nombre = os.path.relpath(ruta, os.path.join(RAIZ, "sql")).replace("\\", "/")
        with open(ruta, encoding="utf-8") as archivo:
            plantilla = archivo.read()
        # Marcas del .env: {{SRID}}, {{REPL_USER}}, {{PORT_CARTAGO}}, ...
        for clave, valor in ENV.items():
            plantilla = plantilla.replace("{{" + clave + "}}", valor)
        # Marcas del nodo
        plantilla = plantilla.replace("{{NODO}}", nodo)
        plantilla = plantilla.replace("{{CAMPUS_ID}}", "NULL" if campus_id is None else str(campus_id))

        if "por_esquema" in nombre:
            # Se ejecuta una vez por cada esquema de campus
            for esquema_id, esquema in CAMPUS:
                sql = plantilla.replace("{{ESQUEMA}}", esquema)
                sql = sql.replace("{{ESQUEMA_ID}}", str(esquema_id))
                cursor.execute(sql)
            print(f"  [{nodo}] {nombre} (x5 esquemas)")
        else:
            cursor.execute(plantilla)
            print(f"  [{nodo}] {nombre}")
    conexion.close()


def main():
    """Levanta Docker, ejecuta los SQL en cada nodo, carga los datos, arma la replicación y publica los estilos."""
    reset = "--reset" in sys.argv
    sin_datos = "--sin-datos" in sys.argv

    print("1. Docker")
    if hay_instalacion_de_otra_carpeta():
        reset = True  # sus datos tienen otras contraseñas: no se pueden reutilizar
    if reset:
        print("  --reset: se borran contenedores y volúmenes")
        docker_compose("down", "-v", "--remove-orphans")
        docker_compose("build")
    # Sin --build: si los contenedores ya corren, no se recrean (no se corta la replicación)
    docker_compose("up", "-d")

    print("2. Esperando a que los nodos respondan")
    for nodo in NODOS:
        if not esperar_nodo(nodo):
            sys.exit(f"ERROR: el nodo {nodo} no respondió a tiempo")
        print(f"  {nodo}: listo")

    print("3. Scripts SQL")
    for nodo in NODOS:
        ejecutar_sql_nodo(nodo)

    if not sin_datos:
        print("4. Datos de ejemplo")
        import cargar_datos
        cargar_datos.main()

    print("5. Replicación lógica (nivel 1 y nivel 2)")
    import replicacion
    replicacion.configurar()

    print("6. Estilos de QGIS (layer_styles en el central)")
    import generar_estilos
    generar_estilos.publicar_faltantes()

    print("Listo. Para ver el estado: python scripts/estado_nodos.py")


if __name__ == "__main__":
    main()
