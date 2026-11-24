"""
Commit en dos fases (2PC) entre DOS nodos: el central y un campus.

Caso: registrar un usuario nuevo en el CENTRAL y, al mismo tiempo, crear su punto
de interés inicial ("Oficina de <usuario>") en el nodo de SU CAMPUS.
Las dos cosas deben quedar hechas juntas, o ninguna.

Cómo funciona 2PC (este script es el "coordinador"):
    Fase 1 (preparar): cada nodo hace su trabajo y ejecuta PREPARE TRANSACTION.
                       Un nodo preparado garantiza que podrá confirmar, incluso si se reinicia.
    Fase 2 (decidir):  si TODOS prepararon bien -> COMMIT PREPARED en todos.
                       si ALGUNO falló          -> ROLLBACK PREPARED en todos.

Con psycopg2:
    conexion.tpc_begin(xid)   inicia la transacción distribuida
    conexion.tpc_prepare()    PREPARE TRANSACTION
    conexion.tpc_commit()     COMMIT PREPARED
    conexion.tpc_rollback()   ROLLBACK PREPARED (o ROLLBACK si no se había preparado)
    conexion.tpc_recover()    lista las transacciones preparadas pendientes en el nodo

Escenarios:
    a) éxito: los dos nodos preparan y se confirma en ambos
    b) falla en el campus (dato inválido): se deshace en ambos
    c) el coordinador "se cae" después de preparar: las transacciones quedan
       pendientes en los dos nodos (pg_prepared_xacts) y luego se recuperan

Uso: python scripts/demo_2pc.py
"""
import uuid

import psycopg2

from comun import NODOS, SRID, conectar, contar

CAMPUS_DEMO = "san_carlos"
CAMPUS_ID = NODOS[CAMPUS_DEMO]["campus_id"]


def nuevo_xid(conexion, gtrid, nodo):
    """Identificador de la transacción en un nodo: '<id de la operación>-<nodo>'.
    Es el nombre que se ve en pg_prepared_xacts (PREPARE TRANSACTION '<nombre>')."""
    return f"{gtrid}-{nodo}"


def trabajo_central(conexion, usuario):
    conexion.cursor().execute(
        "INSERT INTO public.usuarios (usuario, clave_hash, campus_id) "
        "VALUES (%s, crypt('clave123', gen_salt('bf')), %s)", (usuario, CAMPUS_ID))


def trabajo_campus(conexion, usuario, tipo="otro"):
    conexion.cursor().execute(
        f"INSERT INTO {CAMPUS_DEMO}.puntos_interes (nombre, tipo, descripcion, geom) "
        f"VALUES (%s, %s, 'Creado con 2PC', ST_SetSRID(ST_MakePoint(495000, 1145000), {SRID}))",
        (f"Oficina de {usuario}", tipo))


def existe_en_ambos(usuario):
    en_central = contar("central", "SELECT count(*) FROM public.usuarios WHERE usuario = %s", (usuario,))
    en_campus = contar(CAMPUS_DEMO, f"SELECT count(*) FROM {CAMPUS_DEMO}.puntos_interes WHERE nombre = %s",
                       (f"Oficina de {usuario}",))
    return en_central, en_campus


def registrar_usuario_2pc(usuario, tipo="otro"):
    """Coordinador 2PC completo. Devuelve True si confirmó, False si deshizo."""
    gtrid = f"sigtec-{uuid.uuid4().hex[:8]}"
    central = conectar("central", autocommit=False)
    campus = conectar(CAMPUS_DEMO, autocommit=False)
    central.tpc_begin(nuevo_xid(central, gtrid, "central"))
    campus.tpc_begin(nuevo_xid(campus, gtrid, CAMPUS_DEMO))
    try:
        # Fase 1: trabajo + PREPARE en cada nodo
        trabajo_central(central, usuario)
        trabajo_campus(campus, usuario, tipo)
        central.tpc_prepare()
        campus.tpc_prepare()
    except psycopg2.Error as error:
        print(f"    falla en la fase 1: {error.diag.message_primary}")
        print("    -> ROLLBACK en los dos nodos")
        central.tpc_rollback()
        campus.tpc_rollback()
        central.close()
        campus.close()
        return False
    # Fase 2: todos prepararon -> COMMIT PREPARED en ambos
    print(f"    los dos nodos prepararon ({gtrid}) -> COMMIT PREPARED en ambos")
    central.tpc_commit()
    campus.tpc_commit()
    central.close()
    campus.close()
    return True


def preparadas(nodo):
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    cursor.execute("SELECT gid FROM pg_prepared_xacts ORDER BY gid")
    gids = [fila[0] for fila in cursor.fetchall()]
    conexion.close()
    return gids


def escenario_c(usuario):
    """El coordinador prepara en los dos nodos y 'se cae' antes de decidir."""
    gtrid = f"sigtec-{uuid.uuid4().hex[:8]}"
    central = conectar("central", autocommit=False)
    campus = conectar(CAMPUS_DEMO, autocommit=False)
    central.tpc_begin(nuevo_xid(central, gtrid, "central"))
    campus.tpc_begin(nuevo_xid(campus, gtrid, CAMPUS_DEMO))
    trabajo_central(central, usuario)
    trabajo_campus(campus, usuario)
    central.tpc_prepare()
    campus.tpc_prepare()
    # El coordinador se cae: cierra las conexiones sin COMMIT ni ROLLBACK
    central.close()
    campus.close()
    print("    el coordinador preparó y se cayó antes de decidir")
    print(f"    pendientes en central:    {preparadas('central')}")
    print(f"    pendientes en {CAMPUS_DEMO}: {preparadas(CAMPUS_DEMO)}")
    print(f"    ¿se ven los datos? (central, campus) = {existe_en_ambos(usuario)}  <- aún no")

    # Recuperación: un coordinador nuevo busca las transacciones pendientes de este gtrid.
    # Como ESTÁN PREPARADAS EN LOS DOS nodos, la decisión correcta es confirmar.
    print("    recuperación: tpc_recover() en cada nodo y COMMIT PREPARED")
    for nodo in ["central", CAMPUS_DEMO]:
        conexion = conectar(nodo, autocommit=False)
        for xid in conexion.tpc_recover():
            if xid.gtrid.startswith(gtrid):
                conexion.tpc_commit(xid)
        conexion.close()
    print(f"    pendientes después: central={preparadas('central')} {CAMPUS_DEMO}={preparadas(CAMPUS_DEMO)}")


def limpiar(usuarios):
    for usuario in usuarios:
        conexion = conectar("central")
        conexion.cursor().execute("DELETE FROM public.usuarios WHERE usuario = %s", (usuario,))
        conexion.close()
        conexion = conectar(CAMPUS_DEMO)
        conexion.cursor().execute(f"DELETE FROM {CAMPUS_DEMO}.puntos_interes WHERE nombre = %s",
                                  (f"Oficina de {usuario}",))
        conexion.close()


def main():
    sufijo = uuid.uuid4().hex[:4]
    usuario_a, usuario_b, usuario_c = f"demo_a_{sufijo}", f"demo_b_{sufijo}", f"demo_c_{sufijo}"

    print(f"a) ÉXITO: registrar {usuario_a} (central) + su oficina ({CAMPUS_DEMO})")
    registrar_usuario_2pc(usuario_a)
    print(f"    resultado (central, campus) = {existe_en_ambos(usuario_a)}  <- debe ser (1, 1)\n")

    print(f"b) FALLA: registrar {usuario_b}, pero el punto de interés tiene un tipo inválido")
    registrar_usuario_2pc(usuario_b, tipo="tipo_invalido")
    print(f"    resultado (central, campus) = {existe_en_ambos(usuario_b)}  <- debe ser (0, 0)\n")

    print(f"c) CAÍDA DEL COORDINADOR después de preparar ({usuario_c})")
    escenario_c(usuario_c)
    print(f"    resultado (central, campus) = {existe_en_ambos(usuario_c)}  <- debe ser (1, 1)\n")

    limpiar([usuario_a, usuario_b, usuario_c])
    print("Datos de la demo borrados.")


if __name__ == "__main__":
    main()
