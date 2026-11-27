"""
Replicación lógica de SIG-TEC en dos niveles.

NIVEL 1 (campus -> central)
    Cada campus publica las 8 tablas de SU esquema:      pub_nivel1_<campus>
    El central se suscribe a cada campus:                 sub_nivel1_<campus>
    Resultado: el central tiene una copia física de cada campus en su propio esquema.

NIVEL 2 (central -> campus)
    El central publica, para cada campus, los esquemas de los OTROS 4
    y la tabla de estilos public.layer_styles:                           pub_nivel2_<campus>
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
    python scripts/replicacion.py resincronizar limon   # reengancha un campus restaurado
"""
import sys
import time

from comun import CAMPUS, ENV, NODOS, conectar

# Tabla de estilos de QGIS: vive en el central y viaja a los campus en el nivel 2
ESTILOS = "public.layer_styles"


def texto_conexion(host):
    """Cadena de conexión que usa el suscriptor para llegar al publicador (por la red docker)."""
    return (f"host={host} port=5432 dbname={ENV['DB_NAME']} "
            f"user={ENV['REPL_USER']} password={ENV['REPL_PASSWORD']}")


def existe(nodo, catalogo, columna, nombre):
    """Devuelve True si en el catálogo del nodo ya existe una publicación o suscripción con ese nombre."""
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    cursor.execute(f"SELECT 1 FROM {catalogo} WHERE {columna} = %s", (nombre,))
    hay = cursor.fetchone() is not None
    conexion.close()
    return hay


def crear_publicacion(nodo, nombre, esquemas, tabla_extra=None):
    """Publica todas las tablas de los esquemas indicados (y opcionalmente una tabla más)."""
    if existe(nodo, "pg_publication", "pubname", nombre):
        print(f"  [{nodo}] publicación {nombre} ya existe")
        return
    sql = f"CREATE PUBLICATION {nombre} FOR TABLES IN SCHEMA {', '.join(esquemas)}"
    if tabla_extra:
        sql += f", TABLE {tabla_extra}"
    conexion = conectar(nodo)
    conexion.cursor().execute(sql)
    conexion.close()
    print(f"  [{nodo}] CREATE PUBLICATION {nombre} ({', '.join(esquemas)}"
          + (f" + {tabla_extra})" if tabla_extra else ")"))


def asegurar_tabla(nodo, publicacion, tabla, nodo_suscriptor, suscripcion):
    """Si la publicación ya existía sin la tabla, la agrega y refresca la suscripción
    (así un ambiente creado antes recibe la tabla nueva sin borrar nada)."""
    esquema, nombre = tabla.split(".")
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    cursor.execute("SELECT 1 FROM pg_publication_tables WHERE pubname = %s AND schemaname = %s AND tablename = %s",
                   (publicacion, esquema, nombre))
    if cursor.fetchone() is None:
        cursor.execute(f"ALTER PUBLICATION {publicacion} ADD TABLE {tabla}")
        print(f"  [{nodo}] ALTER PUBLICATION {publicacion} ADD TABLE {tabla}")
        conexion.close()
        conexion = conectar(nodo_suscriptor)
        conexion.cursor().execute(f"ALTER SUBSCRIPTION {suscripcion} REFRESH PUBLICATION")
        print(f"  [{nodo_suscriptor}] ALTER SUBSCRIPTION {suscripcion} REFRESH PUBLICATION")
    conexion.close()


def crear_suscripcion(nodo, nombre, host_publicador, publicacion):
    """Crea en el nodo una suscripción a la publicación de otro nodo, con copia inicial de los datos."""
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
    """Arma la replicación completa: nivel 1 (campus -> central) y nivel 2 (central -> campus)."""
    print(" Nivel 1: campus -> central")
    for _, campus in CAMPUS:
        crear_publicacion(campus, f"pub_nivel1_{campus}", [campus])
    for _, campus in CAMPUS:
        crear_suscripcion("central", f"sub_nivel1_{campus}", campus, f"pub_nivel1_{campus}")
    esperar_copia_inicial("central")

    print(" Nivel 2: central -> campus (los otros 4 esquemas + los estilos)")
    for _, campus in CAMPUS:
        otros = [otro for _, otro in CAMPUS if otro != campus]
        crear_publicacion("central", f"pub_nivel2_{campus}", otros, ESTILOS)
    for _, campus in CAMPUS:
        crear_suscripcion(campus, f"sub_nivel2_{campus}", "central", f"pub_nivel2_{campus}")
        asegurar_tabla("central", f"pub_nivel2_{campus}", ESTILOS, campus, f"sub_nivel2_{campus}")
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


# ---------------------------------------------------------------------
# Resincronizar un campus (después de restaurarlo)
# ---------------------------------------------------------------------
def quitar_suscripcion(nodo, nombre):
    """Borra una suscripción SIN tocar el slot remoto (puede que ya no exista).
    DISABLE + slot_name = NONE es la forma de soltar una suscripción cuyo publicador cambió."""
    if not existe(nodo, "pg_subscription", "subname", nombre):
        return
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    cursor.execute(f"ALTER SUBSCRIPTION {nombre} DISABLE")
    cursor.execute(f"ALTER SUBSCRIPTION {nombre} SET (slot_name = NONE)")
    cursor.execute(f"DROP SUBSCRIPTION {nombre}")
    conexion.close()
    print(f"  [{nodo}] DROP SUBSCRIPTION {nombre}")


def quitar_slot(nodo, nombre, segundos=30):
    """Borra un slot de replicación que quedó huérfano (espera a que nadie lo use)."""
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    limite = time.time() + segundos
    while time.time() < limite:
        cursor.execute("SELECT active FROM pg_replication_slots WHERE slot_name = %s", (nombre,))
        fila = cursor.fetchone()
        if fila is None:
            break
        if not fila[0]:
            cursor.execute("SELECT pg_drop_replication_slot(%s)", (nombre,))
            print(f"  [{nodo}] pg_drop_replication_slot('{nombre}')")
            break
        time.sleep(1)
    conexion.close()


def vaciar(nodo, esquemas, incluir_estilos=False):
    """TRUNCATE de todas las tablas de los esquemas.
    session_replication_role = replica: así no se disparan los triggers de protección
    (es lo mismo que hace la replicación al aplicar datos). Requiere superusuario."""
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    cursor.execute("SELECT schemaname || '.' || tablename FROM pg_tables WHERE schemaname = ANY(%s)",
                   (list(esquemas),))
    tablas = [fila[0] for fila in cursor.fetchall()]
    if incluir_estilos:
        tablas.append(ESTILOS)
    cursor.execute("SET session_replication_role = replica")
    cursor.execute(f"TRUNCATE {', '.join(tablas)}")
    conexion.close()
    print(f"  [{nodo}] TRUNCATE de {len(tablas)} tablas ({', '.join(esquemas)}{' + estilos' if incluir_estilos else ''})")


def resincronizar(campus):
    """Vuelve a enganchar un campus restaurado con el resto del sistema.

    Después de restaurar un nodo (PITR o respaldo físico):
      - el nodo NO tiene sus slots (pg_basebackup no los copia),
      - sus datos pueden ser "más viejos" que lo que ya tiene el central.
    El nodo restaurado manda sobre SU esquema; el central manda sobre los demás.
    """
    otros = [c for _, c in CAMPUS if c != campus]
    print(f" Resincronizando {campus}")
    # 1. Soltar las suscripciones y slots viejos de este campus (nivel 1 y nivel 2)
    quitar_suscripcion("central", f"sub_nivel1_{campus}")
    quitar_slot(campus, f"sub_nivel1_{campus}")
    quitar_suscripcion(campus, f"sub_nivel2_{campus}")
    quitar_slot("central", f"sub_nivel2_{campus}")
    # 2. Vaciar las copias: la del campus en el central (el TRUNCATE viaja a los otros
    #    4 campus por el nivel 2) y las de los otros campus en el nodo restaurado.
    vaciar("central", [campus])
    vaciar(campus, otros, incluir_estilos=True)
    # 3. Volver a crear el nivel 1 y el nivel 2 con copia inicial
    crear_publicacion(campus, f"pub_nivel1_{campus}", [campus])
    crear_suscripcion("central", f"sub_nivel1_{campus}", campus, f"pub_nivel1_{campus}")
    esperar_copia_inicial("central")
    crear_suscripcion(campus, f"sub_nivel2_{campus}", "central", f"pub_nivel2_{campus}")
    esperar_copia_inicial(campus)
    reactivar()


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
    """Muestra las publicaciones y suscripciones de cada nodo."""
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
    if accion == "resincronizar":
        resincronizar(sys.argv[2])
    else:
        {"configurar": configurar, "estado": estado, "quitar": quitar, "reactivar": reactivar}[accion]()
