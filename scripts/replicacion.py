"""
Replicación lógica de SIG-TEC en dos niveles.

NIVEL 1 (campus -> central)
    Cada campus publica las 8 tablas de SU esquema:      pub_nivel1_<campus>
    El central se suscribe a cada campus:                 sub_nivel1_<campus>
    Resultado: el central tiene una copia física de cada campus en su propio esquema.

NIVEL 2 (central -> campus)
    El central publica, para cada campus, los esquemas de los OTROS 4:   pub_nivel2_<campus>
    Cada campus se suscribe al central:                                  sub_nivel2_<campus>
    Resultado: cada campus tiene su esquema editable + los otros 4 como copia de consulta.
    Nunca se le envía a un campus su propio esquema, así los datos no "dan la vuelta".

Detalles importantes:
    - Las tablas ya existen en todos los nodos (init_all.py), requisito para suscribirse.
    - copy_data = true: al crear la suscripción se copia lo que ya existe.
    - El nivel 2 se crea cuando el central terminó la copia inicial del nivel 1.
    - El nombre de la suscripción es también el nombre del slot en el publicador,
      por eso cada uno es distinto (sub_nivel2_cartago, sub_nivel2_san_jose, ...).

Uso:
    python scripts/replicacion.py            # crea lo que falte (se puede repetir)
    python scripts/replicacion.py estado     # muestra publicaciones y suscripciones
    python scripts/replicacion.py quitar     # borra todas las suscripciones y publicaciones
    python scripts/replicacion.py reactivar  # relanza suscripciones que quedaron sin proceso
"""
import sys
import time

from comun import CAMPUS, ENV, NODOS, conectar


def texto_conexion(host):
    """Cadena de conexión que usa el suscriptor para llegar al publicador (por la red docker)."""
    return (f"host={host} port=5432 dbname={ENV['DB_NAME']} "
            f"user={ENV['REPL_USER']} password={ENV['REPL_PASSWORD']}")


def existe(nodo, catalogo, columna, nombre):
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    cursor.execute(f"SELECT 1 FROM {catalogo} WHERE {columna} = %s", (nombre,))
    hay = cursor.fetchone() is not None
    conexion.close()
    return hay


def crear_publicacion(nodo, nombre, esquemas):
    if existe(nodo, "pg_publication", "pubname", nombre):
        print(f"  [{nodo}] publicación {nombre} ya existe")
        return
    conexion = conectar(nodo)
    conexion.cursor().execute(
        f"CREATE PUBLICATION {nombre} FOR TABLES IN SCHEMA {', '.join(esquemas)}")
    conexion.close()
    print(f"  [{nodo}] CREATE PUBLICATION {nombre} ({', '.join(esquemas)})")


def crear_suscripcion(nodo, nombre, host_publicador, publicacion):
    if existe(nodo, "pg_subscription", "subname", nombre):
        print(f"  [{nodo}] suscripción {nombre} ya existe")
        return
    # CREATE SUBSCRIPTION no puede ir dentro de una transacción: conectar() usa autocommit
    conexion = conectar(nodo)
    conexion.cursor().execute(
        f"CREATE SUBSCRIPTION {nombre} CONNECTION '{texto_conexion(host_publicador)}' "
        f"PUBLICATION {publicacion} WITH (copy_data = true)")
    conexion.close()
    print(f"  [{nodo}] CREATE SUBSCRIPTION {nombre} -> {host_publicador}.{publicacion}")


def esperar_copia_inicial(nodo, segundos=120):
    """Espera a que todas las tablas suscritas del nodo estén en estado 'r' (listas)."""
    limite = time.time() + segundos
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    while time.time() < limite:
        cursor.execute("SELECT count(*) FILTER (WHERE srsubstate <> 'r'), count(*) FROM pg_subscription_rel")
        pendientes, total = cursor.fetchone()
        if pendientes == 0:
            conexion.close()
            print(f"  [{nodo}] copia inicial lista ({total} tablas)")
            return
        time.sleep(1)
    conexion.close()
    sys.exit(f"ERROR: {nodo} no terminó la copia inicial a tiempo")


def configurar():
    print(" Nivel 1: campus -> central")
    for _, campus in CAMPUS:
        crear_publicacion(campus, f"pub_nivel1_{campus}", [campus])
    for _, campus in CAMPUS:
        crear_suscripcion("central", f"sub_nivel1_{campus}", campus, f"pub_nivel1_{campus}")
    esperar_copia_inicial("central")

    print(" Nivel 2: central -> campus")
    for _, campus in CAMPUS:
        otros = [otro for _, otro in CAMPUS if otro != campus]
        crear_publicacion("central", f"pub_nivel2_{campus}", otros)
    for _, campus in CAMPUS:
        crear_suscripcion(campus, f"sub_nivel2_{campus}", "central", f"pub_nivel2_{campus}")
    for _, campus in CAMPUS:
        esperar_copia_inicial(campus)

    print(" Revisando que todas las suscripciones estén corriendo")
    reactivar()


def suscripciones_sin_proceso(nodo):
    """Suscripciones activas del nodo cuyo proceso de aplicación NO está corriendo."""
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    cursor.execute("""SELECT s.subname FROM pg_subscription s
                      LEFT JOIN pg_stat_subscription w ON w.subid = s.oid AND w.relid IS NULL
                      WHERE s.subenabled AND w.pid IS NULL ORDER BY 1""")
    nombres = [fila[0] for fila in cursor.fetchall()]
    conexion.close()
    return nombres


def reactivar(segundos=60):
    """Despierta las suscripciones que quedaron sin proceso.

    Si al arrancar un nodo su publicador todavía no estaba listo, el proceso de la
    suscripción falla y PostgreSQL puede tardar hasta 3 minutos en reintentar.
    DISABLE + ENABLE hace que lo vuelva a lanzar de inmediato.
    """
    limite = time.time() + segundos
    while time.time() < limite:
        caidas = [(nodo, nombre) for nodo in NODOS for nombre in suscripciones_sin_proceso(nodo)]
        if not caidas:
            print("  las 10 suscripciones tienen su proceso corriendo")
            return True
        for nodo, nombre in caidas:
            conexion = conectar(nodo)
            conexion.cursor().execute(f"ALTER SUBSCRIPTION {nombre} DISABLE")
            conexion.cursor().execute(f"ALTER SUBSCRIPTION {nombre} ENABLE")
            conexion.close()
            print(f"  [{nodo}] {nombre} sin proceso -> DISABLE + ENABLE")
        time.sleep(3)
    print("  AVISO: hay suscripciones que no arrancan (revise que todos los nodos estén arriba)")
    return False


def quitar():
    """Borra suscripciones (y con ellas sus slots remotos) y luego publicaciones."""
    for nodo in NODOS:
        conexion = conectar(nodo)
        cursor = conexion.cursor()
        cursor.execute("SELECT subname FROM pg_subscription")
        for (nombre,) in cursor.fetchall():
            cursor.execute(f"DROP SUBSCRIPTION {nombre}")
            print(f"  [{nodo}] DROP SUBSCRIPTION {nombre}")
        conexion.close()
    for nodo in NODOS:
        conexion = conectar(nodo)
        cursor = conexion.cursor()
        cursor.execute("SELECT pubname FROM pg_publication")
        for (nombre,) in cursor.fetchall():
            cursor.execute(f"DROP PUBLICATION {nombre}")
            print(f"  [{nodo}] DROP PUBLICATION {nombre}")
        conexion.close()


def estado():
    for nodo in NODOS:
        conexion = conectar(nodo)
        cursor = conexion.cursor()
        cursor.execute("""SELECT p.pubname, string_agg(DISTINCT n.nspname, ', ')
                          FROM pg_publication p
                          JOIN pg_publication_namespace pn ON pn.pnpubid = p.oid
                          JOIN pg_namespace n ON n.oid = pn.pnnspid
                          GROUP BY p.pubname ORDER BY 1""")
        for nombre, esquemas in cursor.fetchall():
            print(f"  [{nodo}] publica    {nombre}: {esquemas}")
        cursor.execute("""SELECT subname, subenabled, subpublications::text FROM pg_subscription ORDER BY 1""")
        for nombre, activa, publicaciones in cursor.fetchall():
            print(f"  [{nodo}] se suscribe {nombre} -> {publicaciones} {'(activa)' if activa else '(DESACTIVADA)'}")
        conexion.close()


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "configurar"
    {"configurar": configurar, "estado": estado, "quitar": quitar, "reactivar": reactivar}[accion]()
