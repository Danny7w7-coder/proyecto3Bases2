"""
Respaldos de SIG-TEC. Cada nodo tiene su propia estrategia:

  LÓGICO  (pg_dump)        base completa + el esquema propio del nodo, formato custom (-Fc)
  FÍSICO  (pg_basebackup)  copia binaria de todo el cluster + el WAL necesario (-X fetch)
  WAL     (archive_mode)   cada segmento de WAL se copia a /wal_archive (volumen aparte)
                           -> permite PITR: respaldo físico + WAL hasta una hora exacta

Los archivos quedan en backups/<nodo>/logico y backups/<nodo>/fisico, con fecha y hora en el nombre.
Los comandos corren DENTRO del contenedor (docker exec) y la salida se guarda directo en el archivo.

Uso:
    python scripts/respaldos.py logico  [nodo|todos]
    python scripts/respaldos.py fisico  [nodo|todos]
    python scripts/respaldos.py verificar <nodo>     # restaura el último lógico en una base aparte y compara
    python scripts/respaldos.py listar
"""
import datetime
import glob
import os
import subprocess
import sys
import time

from comun import ENV, NODOS, RAIZ, conectar, contar

CARPETA = os.path.join(RAIZ, "backups")
BASE = ENV["DB_NAME"]
USUARIO = ENV["DB_USER"]


def contenedor(nodo):
    """Nombre del contenedor de Docker de un nodo (sigtec_<nodo>)."""
    return f"sigtec_{nodo}"


def marca_de_tiempo():
    """Fecha y hora actual, para el nombre de los archivos de respaldo."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def carpeta(nodo, tipo):
    """Carpeta backups/<nodo>/<tipo>. Se crea si no existe."""
    ruta = os.path.join(CARPETA, nodo, tipo)
    os.makedirs(ruta, exist_ok=True)
    return ruta


def docker_exec_a_archivo(nodo, comando, archivo):
    """Corre un comando en el contenedor y guarda su salida (stdout) en un archivo del anfitrión."""
    with open(archivo, "wb") as salida:
        resultado = subprocess.run(["docker", "exec", contenedor(nodo), *comando],
                                   stdout=salida, stderr=subprocess.PIPE)
    if resultado.returncode != 0:
        os.remove(archivo)
        raise RuntimeError(f"{' '.join(comando)} falló en {nodo}: {resultado.stderr.decode(errors='replace')}")
    return os.path.getsize(archivo)


def tamano(bytes_):
    """Tamaño en KB o MB, para mostrarlo en pantalla."""
    return f"{bytes_ / 1024:.0f} KB" if bytes_ < 1024 * 1024 else f"{bytes_ / 1024 / 1024:.1f} MB"


# ---------------------------------------------------------------------
# Respaldo lógico
# ---------------------------------------------------------------------
def esquema_propio(nodo):
    """El esquema que le pertenece al nodo. En el central: public (usuarios, estilos, nodos)."""
    return "public" if nodo == "central" else nodo


def respaldo_logico(nodo):
    """pg_dump de la base completa y del esquema propio. Devuelve las dos rutas."""
    fecha = marca_de_tiempo()
    destino = carpeta(nodo, "logico")
    completo = os.path.join(destino, f"{nodo}_completo_{fecha}.dump")
    esquema = esquema_propio(nodo)
    parcial = os.path.join(destino, f"{nodo}_esquema_{esquema}_{fecha}.dump")
    t = docker_exec_a_archivo(nodo, ["pg_dump", "-U", USUARIO, "-d", BASE, "-Fc"], completo)
    print(f"  [{nodo}] pg_dump completo          -> {os.path.relpath(completo, RAIZ)} ({tamano(t)})")
    t = docker_exec_a_archivo(nodo, ["pg_dump", "-U", USUARIO, "-d", BASE, "-Fc", "-n", esquema], parcial)
    print(f"  [{nodo}] pg_dump esquema {esquema:<10} -> {os.path.relpath(parcial, RAIZ)} ({tamano(t)})")
    return completo, parcial


def ultimo(nodo, tipo, patron):
    """Ruta del respaldo más reciente de un nodo que coincide con el patrón."""
    archivos = sorted(glob.glob(os.path.join(CARPETA, nodo, tipo, patron)))
    if not archivos:
        raise FileNotFoundError(f"no hay respaldos {tipo} de {nodo} ({patron})")
    return archivos[-1]


def verificar_logico(nodo):
    """Restaura el último respaldo lógico completo en una base nueva del mismo nodo
    y compara la cantidad de filas de cada capa con la base original."""
    archivo = ultimo(nodo, "logico", f"{nodo}_completo_*.dump")
    # Base temporal y vacía donde se restaura la copia (la base real no se toca)
    prueba = "verificacion_respaldo"
    conexion = conectar(nodo)
    conexion.cursor().execute(f"DROP DATABASE IF EXISTS {prueba}")
    conexion.cursor().execute(f"CREATE DATABASE {prueba}")
    conexion.close()
    # --no-subscriptions / --no-publications: la copia de prueba no debe replicar nada
    with open(archivo, "rb") as entrada:
        resultado = subprocess.run(
            ["docker", "exec", "-i", contenedor(nodo), "pg_restore", "-U", USUARIO, "-d", prueba,
             "--no-subscriptions", "--no-publications"],
            stdin=entrada, stderr=subprocess.PIPE)
    if resultado.returncode != 0:
        raise RuntimeError(f"pg_restore falló: {resultado.stderr.decode(errors='replace')[-1500:]}")

    # Contar filas tabla por tabla en la base original y en la copia restaurada
    import psycopg2
    original = conectar(nodo)
    copia = psycopg2.connect(host="127.0.0.1", port=NODOS[nodo]["puerto"], dbname=prueba,
                             user=USUARIO, password=ENV["DB_PASSWORD"])
    c_original, c_copia = original.cursor(), copia.cursor()
    # (spatial_ref_sys es el catálogo de PostGIS: se omite para que el total sea solo de datos del proyecto)
    c_original.execute("SELECT schemaname, tablename FROM pg_tables WHERE schemaname IN "
                       "('public', 'cartago', 'san_jose', 'san_carlos', 'alajuela', 'limon') "
                       "AND tablename <> 'spatial_ref_sys' ORDER BY 1, 2")
    total_original = total_copia = 0
    for esquema, tabla in c_original.fetchall():
        c_original.execute(f"SELECT count(*) FROM {esquema}.{tabla}")
        c_copia.execute(f"SELECT count(*) FROM {esquema}.{tabla}")
        total_original += c_original.fetchone()[0]
        total_copia += c_copia.fetchone()[0]
    original.close()
    copia.close()

    # Se borra la base temporal: solo servía para comprobar el respaldo
    conexion = conectar(nodo)
    conexion.cursor().execute(f"DROP DATABASE {prueba}")
    conexion.close()
    print(f"  [{nodo}] {os.path.basename(archivo)} restaurado en '{prueba}': "
          f"{total_copia} filas (original {total_original}) -> {'OK' if total_copia == total_original else 'DIFERENTE'}")
    return total_original, total_copia


# ---------------------------------------------------------------------
# Respaldo físico
# ---------------------------------------------------------------------
def respaldo_fisico(nodo):
    """pg_basebackup: un .tar.gz con todo el cluster y el WAL necesario para arrancarlo.
    -D -     escribe el tar en la salida estándar (se guarda directo en el anfitrión)
    -Ft -z   formato tar comprimido
    -X fetch incluye el WAL generado durante el respaldo
    -c fast  hace el checkpoint de inmediato"""
    inicio = time.time()
    archivo = os.path.join(carpeta(nodo, "fisico"), f"{nodo}_base_{marca_de_tiempo()}.tar.gz")
    t = docker_exec_a_archivo(nodo, ["pg_basebackup", "-U", USUARIO, "-D", "-", "-Ft", "-z",
                                     "-X", "fetch", "-c", "fast"], archivo)
    print(f"  [{nodo}] pg_basebackup -> {os.path.relpath(archivo, RAIZ)} ({tamano(t)}, {time.time() - inicio:.1f} s)")
    return archivo


def forzar_archivo_wal(nodo, segundos=60):
    """Cierra el segmento de WAL actual (pg_switch_wal) y espera a que quede archivado.
    Así el WAL con los últimos cambios ya está en /wal_archive."""
    # pg_switch_wal() devuelve la posición justo DESPUÉS del segmento que se cerró.
    # Se resta 1 para obtener el nombre de ese segmento cerrado. Sin el "- 1", si el nodo
    # no tuvo cambios (pg_switch_wal no cierra nada) se esperaría un segmento que aún no termina.
    nombre = contar(nodo, "SELECT pg_walfile_name(pg_switch_wal() - 1)")
    limite = time.time() + segundos
    while time.time() < limite:
        ultimo_archivado = contar(nodo, "SELECT coalesce(last_archived_wal, '') FROM pg_stat_archiver")
        if ultimo_archivado[:24] >= nombre:
            return nombre
        time.sleep(0.5)
    raise TimeoutError(f"{nodo}: el WAL {nombre} no se archivó a tiempo")


def listar():
    """Muestra los respaldos guardados y el estado del archivado de WAL de cada nodo."""
    for nodo in NODOS:
        for tipo in ["logico", "fisico"]:
            for ruta in sorted(glob.glob(os.path.join(CARPETA, nodo, tipo, "*"))):
                print(f"  {nodo:<11} {tipo:<7} {os.path.basename(ruta):<55} {tamano(os.path.getsize(ruta))}")
    print("\n  WAL archivado por nodo (pg_stat_archiver):")
    for nodo in NODOS:
        archivados, fallidos, ultimo_wal = conectar_y_leer(nodo)
        print(f"  {nodo:<11} archivados={archivados} fallidos={fallidos} último={ultimo_wal}")


def conectar_y_leer(nodo):
    """Lee de pg_stat_archiver cuántos WAL se archivaron, cuántos fallaron y cuál fue el último."""
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    cursor.execute("SELECT archived_count, failed_count, last_archived_wal FROM pg_stat_archiver")
    fila = cursor.fetchone()
    conexion.close()
    return fila


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "listar"
    destino = sys.argv[2] if len(sys.argv) > 2 else "todos"
    nodos = list(NODOS) if destino == "todos" else [destino]
    if accion == "logico":
        for n in nodos:
            respaldo_logico(n)
    elif accion == "fisico":
        for n in nodos:
            respaldo_fisico(n)
    elif accion == "verificar":
        for n in nodos:
            verificar_logico(n)
    else:
        listar()
