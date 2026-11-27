"""
Recuperación de un nodo de SIG-TEC.

  pitr <nodo> "<fecha hora>"   Respaldo físico + WAL hasta esa hora exacta (Point In Time Recovery).
                               La hora es la del servidor (UTC), como la muestra SELECT now().
  fisico <nodo>                Último respaldo físico + TODO el WAL archivado (estado más reciente).
  desde_central <campus>       Nodo nuevo y vacío: estructura con los SQL del proyecto y sus datos
                               recuperados desde el central con replicación lógica.

Al final de los tres se corre replicacion.resincronizar(), que vuelve a enganchar el nodo.

Cómo funciona la restauración física:
  1. Se detiene el contenedor.
  2. Un contenedor auxiliar borra el volumen de datos y descomprime ahí el respaldo (pg_basebackup).
  3. Se crea recovery.signal y se agrega a postgresql.auto.conf:
        restore_command = 'cp /wal_archive/%f %p'     (de dónde sacar el WAL archivado)
        recovery_target_time = '...'                  (solo en PITR: hasta qué hora)
        recovery_target_action = 'promote'            (al llegar, abrir la base normal)
  4. Se enciende: PostgreSQL aplica el WAL y se promueve.
  5. Se quitan esos parámetros con ALTER SYSTEM RESET.

Uso:
    python scripts/restaurar.py pitr san_carlos "2026-11-24 20:15:30"
    python scripts/restaurar.py fisico limon
    python scripts/restaurar.py desde_central limon
"""
import subprocess
import sys
import time

import replicacion
from comun import NODOS, RAIZ, conectar, contar, esperar_hasta, esperar_nodo
from respaldos import forzar_archivo_wal, ultimo

IMAGEN = "sigtec-nodo:latest"


def compose(*argumentos):
    """Ejecuta 'docker compose ...' en la carpeta del proyecto. Falla si el comando falla."""
    subprocess.run(["docker", "compose", *argumentos], cwd=RAIZ, check=True, capture_output=True)


def nombre_volumen(nodo, tipo):
    """Nombre real del volumen de Docker (ej. sigtec_limon_data), buscado por las etiquetas de compose
    (solo los de este proyecto, por si quedaron volúmenes viejos de otras instalaciones)."""
    resultado = subprocess.run(["docker", "volume", "ls", "-q",
                                "--filter", "label=com.docker.compose.project=sigtec",
                                "--filter", f"label=com.docker.compose.volume={nodo}_{tipo}"],
                               capture_output=True, text=True, check=True)
    nombres = resultado.stdout.split()
    if not nombres:
        raise RuntimeError(f"no existe el volumen {nodo}_{tipo}")
    return nombres[0]


def auxiliar(volumen, punto_montaje, script, entrada=None):
    """Corre un script bash en un contenedor auxiliar con el volumen montado."""
    resultado = subprocess.run(["docker", "run", "--rm", "-i", "-v", f"{volumen}:{punto_montaje}",
                                "--entrypoint", "bash", IMAGEN, "-c", script],
                               stdin=entrada, capture_output=True)
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.decode(errors="replace"))


def esta_corriendo(nodo):
    """Devuelve True si el contenedor del nodo está encendido."""
    resultado = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", f"sigtec_{nodo}"],
                               capture_output=True, text=True)
    return resultado.stdout.strip() == "true"


def mostrar_log_recuperacion(nodo):
    """Muestra las líneas importantes del registro de PostgreSQL durante la recuperación."""
    resultado = subprocess.run(["docker", "logs", "--since", "5m", f"sigtec_{nodo}"],
                               capture_output=True, text=True, errors="replace")
    claves = ("recovery stopping", "redo done", "archive recovery complete", "selected new timeline",
              "starting point-in-time recovery", "consistent recovery state")
    for linea in (resultado.stdout + resultado.stderr).splitlines():
        if any(c in linea for c in claves):
            print("    log:", linea.split("LOG:", 1)[-1].strip())


# ---------------------------------------------------------------------
def restaurar_fisico(nodo, archivo=None, hasta=None):
    """Restaura el respaldo físico del nodo y aplica el WAL (hasta 'hasta' si se indica)."""
    inicio = time.time()
    archivo = archivo or ultimo(nodo, "fisico", f"{nodo}_base_*.tar.gz")
    print(f" Restaurando {nodo} desde {archivo.split('backups')[-1]}" + (f" hasta {hasta}" if hasta else ""))

    if esta_corriendo(nodo):
        # Que el WAL más reciente quede archivado antes de apagar
        print(f"  WAL archivado hasta {forzar_archivo_wal(nodo)}")
        compose("stop", nodo)
        print(f"  [{nodo}] detenido")
    compose("up", "--no-start", nodo)  # crea contenedor y volumen si no existen

    configuracion = ["restore_command = 'cp /wal_archive/%f %p'"]
    if hasta:
        configuracion += [f"recovery_target_time = '{hasta}'", "recovery_target_action = 'promote'"]
    script = ("set -e\n"
              "find /data -mindepth 1 -delete\n"                 # vaciar el volumen
              "tar -xzf - -C /data\n"                            # el respaldo llega por stdin
              "touch /data/recovery.signal\n"
              "cat >> /data/postgresql.auto.conf <<'FIN'\n" + "\n".join(configuracion) + "\nFIN\n"
              "chown -R postgres:postgres /data\n"
              "chmod 700 /data\n")
    with open(archivo, "rb") as entrada:
        auxiliar(nombre_volumen(nodo, "data"), "/data", script, entrada)
    print(f"  [{nodo}] respaldo descomprimido en el volumen + recovery.signal")

    compose("start", nodo)
    esperar_nodo(nodo, 180)
    esperar_hasta(lambda: contar(nodo, "SELECT NOT pg_is_in_recovery()"), 180)
    conexion = conectar(nodo)
    for parametro in ["restore_command", "recovery_target_time", "recovery_target_action"]:
        conexion.cursor().execute(f"ALTER SYSTEM RESET {parametro}")
    conexion.cursor().execute("SELECT pg_reload_conf()")
    conexion.close()
    mostrar_log_recuperacion(nodo)
    print(f"  [{nodo}] recuperado y abierto (timeline {contar(nodo, 'SELECT timeline_id FROM pg_control_checkpoint()')}),"
          f" {time.time() - inicio:.1f} s")
    return time.time() - inicio


def pitr(nodo, hasta):
    """Recupera un campus hasta una hora exacta y vuelve a enganchar su replicación. Devuelve los tiempos de cada parte."""
    t_restaurar = restaurar_fisico(nodo, hasta=hasta)
    t0 = time.time()
    replicacion.resincronizar(nodo)
    return t_restaurar, time.time() - t0


def fisico(nodo):
    """Recupera un campus con su último respaldo físico y todo el WAL, y vuelve a enganchar su replicación. Devuelve los tiempos de cada parte."""
    t_restaurar = restaurar_fisico(nodo)
    t0 = time.time()
    replicacion.resincronizar(nodo)
    return t_restaurar, time.time() - t0


def desde_central(campus):
    """Nodo nuevo y vacío. Sus datos se recuperan de la copia que tiene el central (nivel 1)."""
    import init_all
    inicio = time.time()
    print(f" Recreando {campus} vacío y recuperándolo desde el central")
    if esta_corriendo(campus):
        compose("stop", campus)
    compose("up", "--no-start", campus)

    # El WAL archivado del nodo viejo se aparta: el nodo nuevo empieza otra vez en el
    # segmento 000000010000000000000001 y chocaría con los nombres viejos.
    apartado = f"/wal_archive/anterior_{int(time.time())}"
    auxiliar(nombre_volumen(campus, "wal"), "/wal_archive",
             f"mkdir -p {apartado} && "
             f"find /wal_archive -maxdepth 1 -type f -exec mv {{}} {apartado}/ \\; ; "
             f"chown -R postgres:postgres /wal_archive")
    # Volumen de datos vacío -> al arrancar, la imagen crea una base nueva (initdb)
    auxiliar(nombre_volumen(campus, "data"), "/data", "find /data -mindepth 1 -delete")
    compose("start", campus)
    esperar_nodo(campus, 180)
    print(f"  [{campus}] base nueva creada (initdb)")

    # 1. Estructura: los mismos SQL del proyecto
    init_all.ejecutar_sql_nodo(campus)

    # 2. Rescate de SU esquema desde el central (publicación y suscripción temporales)
    replicacion.crear_publicacion("central", f"pub_rescate_{campus}", [campus])
    replicacion.crear_suscripcion(campus, f"sub_rescate_{campus}", "central", f"pub_rescate_{campus}")
    replicacion.esperar_copia_inicial(campus)
    conexion = conectar(campus)
    conexion.cursor().execute(f"DROP SUBSCRIPTION sub_rescate_{campus}")
    conexion.close()
    conexion = conectar("central")
    conexion.cursor().execute(f"DROP PUBLICATION pub_rescate_{campus}")
    conexion.close()
    filas = sum(contar(campus, f"SELECT count(*) FROM {campus}.{t}") for t in
                ["edificios", "carreteras", "aceras", "parqueos", "zonas_verdes",
                 "puntos_interes", "iluminacion", "accesibilidad"])
    print(f"  [{campus}] {filas} objetos rescatados desde el central")

    # 3. La secuencia sigue después del id más alto (para no repetir ids)
    union = " UNION ALL ".join(f"SELECT max(id) AS m FROM {campus}.{t}" for t in
                               ["edificios", "carreteras", "aceras", "parqueos", "zonas_verdes",
                                "puntos_interes", "iluminacion", "accesibilidad"])
    conexion = conectar(campus)
    conexion.cursor().execute(f"SELECT setval('{campus}.seq_id', (SELECT max(m) FROM ({union}) t))")
    conexion.close()
    t_restaurar = time.time() - inicio

    # 4. Volver a enganchar el nivel 1 y el nivel 2
    t0 = time.time()
    replicacion.resincronizar(campus)
    return t_restaurar, time.time() - t0


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("pitr", "fisico", "desde_central"):
        sys.exit(__doc__)
    modo, nodo = sys.argv[1], sys.argv[2]
    if nodo not in NODOS or nodo == "central":
        sys.exit("indique un campus: cartago, san_jose, san_carlos, alajuela o limon")
    if modo == "pitr":
        pitr(nodo, sys.argv[3])
    elif modo == "fisico":
        fisico(nodo)
    else:
        desde_central(nodo)
