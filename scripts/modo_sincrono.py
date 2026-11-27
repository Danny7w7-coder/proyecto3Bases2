"""
Modo de confirmación de la replicación (nivel 1: campus -> central).

ASÍNCRONO (por defecto)
    El COMMIT del campus termina apenas se guarda en su propio disco.
    El central recibe el cambio un instante después.
    Si el central está caído, el campus sigue trabajando (autonomía).

SÍNCRONO
    El COMMIT del campus espera a que el central confirme que recibió el cambio.
    Se activa con (en el campus):
        synchronous_standby_names = 'sub_nivel1_<campus>'   (nombre de la suscripción del central)
        synchronous_commit = on
    y (en el central) ALTER SUBSCRIPTION sub_nivel1_<campus> SET (synchronous_commit = on),
    para que el central confirme apenas guarda y no cada ~200 ms.
    Ventaja: si el campus se pierde justo después del COMMIT, el dato ya está en el central.
    Costo: cada COMMIT tarda más, y si el central se cae el COMMIT se queda esperando.

Uso:
    python scripts/modo_sincrono.py estado
    python scripts/modo_sincrono.py activar   [campus|todos]   (por defecto: todos)
    python scripts/modo_sincrono.py desactivar [campus|todos]
    python scripts/modo_sincrono.py demo                      (comparación completa en San Carlos)
"""
import subprocess
import sys
import threading
import time

from comun import CAMPUS, SRID, conectar, contar, esperar_nodo

CAMPUS_DEMO = "san_carlos"


# ---------------------------------------------------------------------
# Activar / desactivar
# ---------------------------------------------------------------------
def sincronizar_suscripcion(campus, valor):
    """En el CENTRAL: synchronous_commit de la suscripción que recibe a este campus.
    Por defecto una suscripción usa 'off': el central guarda en disco cada ~200 ms
    (wal_writer_delay) y recién entonces confirma. Con 'on' confirma apenas guarda."""
    conexion = conectar("central")
    conexion.cursor().execute(f"ALTER SUBSCRIPTION sub_nivel1_{campus} SET (synchronous_commit = '{valor}')")
    conexion.close()


def activar(campus, rapido=True):
    """Activa el modo síncrono en un campus: su COMMIT espera la confirmación del central."""
    if rapido:
        sincronizar_suscripcion(campus, "on")
    conexion = conectar(campus)
    cursor = conexion.cursor()
    cursor.execute(f"ALTER SYSTEM SET synchronous_standby_names = 'sub_nivel1_{campus}'")
    cursor.execute("ALTER SYSTEM SET synchronous_commit = 'on'")
    cursor.execute("SELECT pg_reload_conf()")
    conexion.close()
    time.sleep(0.5)  # dar tiempo a que se aplique la recarga
    print(f"  [{campus}] modo SÍNCRONO: el COMMIT espera al central"
          + ("" if rapido else " (suscripción con synchronous_commit=off)"))


def desactivar(campus):
    """Vuelve al modo asíncrono, que es el valor por defecto."""
    conexion = conectar(campus)
    cursor = conexion.cursor()
    cursor.execute("ALTER SYSTEM RESET synchronous_standby_names")
    cursor.execute("ALTER SYSTEM RESET synchronous_commit")
    cursor.execute("SELECT pg_reload_conf()")
    conexion.close()
    sincronizar_suscripcion(campus, "off")
    time.sleep(0.5)
    print(f"  [{campus}] modo ASÍNCRONO (por defecto)")


def estado():
    """Muestra en qué modo está la replicación de cada campus."""
    for _, campus in CAMPUS:
        conexion = conectar(campus)
        cursor = conexion.cursor()
        cursor.execute("SHOW synchronous_standby_names")
        nombres = cursor.fetchone()[0]
        cursor.execute("SELECT coalesce(max(sync_state), '-') FROM pg_stat_replication")
        sync_state = cursor.fetchone()[0]
        conexion.close()
        modo = "SÍNCRONO" if nombres else "asíncrono"
        print(f"  {campus:<11} {modo:<10} synchronous_standby_names='{nombres}'  sync_state={sync_state}")


# ---------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------
def insertar_uno(conexion, etiqueta):
    """Inserta un punto de interés de prueba. Se usa para medir cuánto tarda un COMMIT."""
    conexion.cursor().execute(
        f"INSERT INTO {CAMPUS_DEMO}.puntos_interes (nombre, tipo, geom) "
        f"VALUES (%s, 'otro', ST_SetSRID(ST_MakePoint(495000, 1145000), {SRID}))", (etiqueta,))


def medir_commits(cantidad=100):
    """Hace 'cantidad' INSERT, cada uno con su propio COMMIT, y devuelve el promedio en ms."""
    conexion = conectar(CAMPUS_DEMO)  # autocommit: cada INSERT es un COMMIT
    inicio = time.perf_counter()
    for _ in range(cantidad):
        insertar_uno(conexion, "DEMO-SYNC")
    total = time.perf_counter() - inicio
    conexion.close()
    return round(total / cantidad * 1000, 2)


def docker(accion, contenedor="sigtec_central"):
    """Ejecuta 'docker <accion> <contenedor>', por ejemplo para apagar o encender el central."""
    subprocess.run(["docker", accion, contenedor], check=True, capture_output=True)


def commit_con_central_caido(sincrono):
    """Apaga el central, intenta un COMMIT en el campus y mide cuánto tarda en terminar."""
    print("  - apagando el central (docker stop sigtec_central)...")
    docker("stop")
    resultado = {}

    def trabajo():
        """Hace un INSERT en otro hilo y mide cuánto tarda su COMMIT."""
        conexion = conectar(CAMPUS_DEMO)
        inicio = time.perf_counter()
        insertar_uno(conexion, "DEMO-SYNC")
        resultado["segundos"] = round(time.perf_counter() - inicio, 2)
        conexion.close()

    # El COMMIT va en otro hilo porque en modo síncrono puede quedarse esperando.
    # Se le dan 6 segundos para terminar
    hilo = threading.Thread(target=trabajo)
    hilo.start()
    hilo.join(timeout=6)

    if hilo.is_alive():
        # Sigue esperando: mostrar qué está haciendo la sesión
        evento = contar(CAMPUS_DEMO, "SELECT string_agg(DISTINCT wait_event, ',') FROM pg_stat_activity "
                                     "WHERE wait_event = 'SyncRep'")
        print(f"  - después de 6 s el COMMIT SIGUE ESPERANDO (wait_event = {evento})")
        print("  - encendiendo el central (docker start sigtec_central)...")
        docker("start")
        hilo.join()
        print(f"  - el COMMIT terminó cuando volvió el central: tardó {resultado['segundos']} s en total")
    else:
        # En modo asíncrono el campus no espera al central
        print(f"  - el COMMIT terminó en {resultado['segundos']} s aunque el central está caído")
        docker("start")
    # El central queda encendido otra vez para lo que sigue
    esperar_nodo("central")
    return resultado["segundos"]


def demo():
    """Compara el modo asíncrono con el síncrono, con el central encendido y apagado, y muestra un resumen."""
    print(f"Demo en el campus {CAMPUS_DEMO}\n")
    # Caso 1: modo asíncrono (el normal del proyecto)
    desactivar(CAMPUS_DEMO)
    print("1. ASÍNCRONO, 100 COMMIT con el central arriba")
    ms_async = medir_commits()
    print(f"  - promedio por COMMIT: {ms_async} ms\n")

    # Caso 2a: síncrono con la suscripción por defecto (el central confirma lento)
    activar(CAMPUS_DEMO, rapido=False)
    print("2a. SÍNCRONO (suscripción por defecto), 100 COMMIT con el central arriba")
    ms_sync_lento = medir_commits()
    print(f"  - promedio por COMMIT: {ms_sync_lento} ms (el central confirma cada ~200 ms)\n")

    # Caso 2b: síncrono con la suscripción ajustada (el central confirma de inmediato)
    activar(CAMPUS_DEMO)
    print("2b. SÍNCRONO (suscripción con synchronous_commit=on), 100 COMMIT con el central arriba")
    ms_sync = medir_commits()
    print(f"  - promedio por COMMIT: {ms_sync} ms\n")

    # Casos 3 y 4: qué pasa con un COMMIT cuando el central no está
    print("3. SÍNCRONO con el central CAÍDO")
    s_sync = commit_con_central_caido(sincrono=True)
    print()

    desactivar(CAMPUS_DEMO)
    print("4. ASÍNCRONO con el central CAÍDO")
    s_async = commit_con_central_caido(sincrono=False)
    print()

    # Esperar a que el central se ponga al día y limpiar las filas de la demo
    time.sleep(3)
    conexion = conectar(CAMPUS_DEMO)
    conexion.cursor().execute(f"DELETE FROM {CAMPUS_DEMO}.puntos_interes WHERE nombre = 'DEMO-SYNC'")
    conexion.close()

    # Tabla final para comparar los dos modos
    print("Resumen")
    print(f"  {'':<34}{'asíncrono':>12}{'síncrono':>12}")
    print(f"  {'COMMIT promedio (central arriba)':<34}{str(ms_async) + ' ms':>12}{str(ms_sync) + ' ms':>12}")
    print(f"  {'  (síncrono con suscripción por defecto)':<34}{'':>12}{str(ms_sync_lento) + ' ms':>12}")
    print(f"  {'COMMIT con el central caído':<34}{str(s_async) + ' s':>12}{str(s_sync) + ' s':>12}")
    print("  (en síncrono, el tiempo con el central caído es lo que tardó en volver el central)")


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "estado"
    destino = sys.argv[2] if len(sys.argv) > 2 else "todos"
    campus_destino = [c for _, c in CAMPUS] if destino == "todos" else [destino]
    if accion == "activar":
        for c in campus_destino:
            activar(c)
    elif accion == "desactivar":
        for c in campus_destino:
            desactivar(c)
    elif accion == "demo":
        demo()
    else:
        estado()
