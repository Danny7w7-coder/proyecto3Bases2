"""
Verifica que las copias de cada capa sean iguales en los 6 nodos.

Para cada esquema y capa se calcula, en cada nodo:
    - cantidad de filas
    - un hash (md5) de todas las filas ordenadas por id
El nodo dueño del esquema es la referencia. Si los otros 5 nodos tienen el mismo
conteo y el mismo hash, la capa está OK. Si no, sale DIFERENTE.

Además muestra el retraso de la replicación:
    - pg_stat_replication     (en cada publicador: a quién envía y cuánto falta)
    - pg_stat_subscription    (en cada suscriptor: último mensaje recibido)

Uso:
    python scripts/verificar_consistencia.py           # tabla completa + retrasos
    python scripts/verificar_consistencia.py --resumen # solo el resultado final
"""
import sys

from cargar_datos import CAPAS
from comun import CAMPUS, NODOS, conectar


def huella(cursor, esquema, capa):
    """Devuelve (filas, hash) de una capa. El hash usa todas las columnas, ordenadas por id."""
    cursor.execute(f"""
        SELECT count(*), coalesce(md5(string_agg(t::text, '|' ORDER BY t.id)), 'vacia')
        FROM {esquema}.{capa} AS t""")
    return cursor.fetchone()


def comparar():
    """Devuelve una lista de (esquema, capa, {nodo: (filas, hash)}, ok)."""
    conexiones = {nodo: conectar(nodo) for nodo in NODOS}
    resultados = []
    for _, esquema in CAMPUS:
        for capa in CAPAS:
            por_nodo = {nodo: huella(conexion.cursor(), esquema, capa)
                        for nodo, conexion in conexiones.items()}
            referencia = por_nodo[esquema]  # el nodo dueño
            ok = all(valor == referencia for valor in por_nodo.values())
            resultados.append((esquema, capa, por_nodo, ok))
    for conexion in conexiones.values():
        conexion.close()
    return resultados


def mostrar_tabla(resultados):
    """Imprime una fila por capa con la cantidad de filas en cada nodo y OK o DIFERENTE."""
    nodos = list(NODOS)
    encabezado = f"{'esquema.capa':<28}" + "".join(f"{n:>11}" for n in nodos) + "   estado"
    print(encabezado)
    print("-" * len(encabezado))
    for esquema, capa, por_nodo, ok in resultados:
        conteos = "".join(f"{por_nodo[n][0]:>11}" for n in nodos)
        print(f"{esquema + '.' + capa:<28}{conteos}   {'OK' if ok else 'DIFERENTE'}")


def mostrar_retrasos():
    """Muestra cuánto falta por replicar en cada publicador y cuándo recibió el último mensaje cada suscriptor."""
    print("\nPublicadores (pg_stat_replication): bytes pendientes de confirmar por cada suscriptor")
    for nodo in NODOS:
        conexion = conectar(nodo)
        cursor = conexion.cursor()
        # Bytes pendientes = posición actual del WAL menos lo que el suscriptor ya confirmó
        cursor.execute("""
            SELECT application_name, state,
                   pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) AS bytes_pendientes,
                   coalesce(replay_lag::text, '0')
            FROM pg_stat_replication ORDER BY 1""")
        for nombre, estado, pendientes, retraso in cursor.fetchall():
            print(f"  {nodo:<11} -> {nombre:<24} {estado:<10} pendiente={int(pendientes or 0)} B  retraso={retraso}")
        conexion.close()

    print("\nSuscriptores (pg_stat_subscription): tiempo desde el último mensaje del publicador")
    for nodo in NODOS:
        conexion = conectar(nodo)
        cursor = conexion.cursor()
        # Segundos desde el último mensaje y errores que lleva cada suscripción
        cursor.execute("""
            SELECT s.subname, round(extract(epoch FROM now() - s.last_msg_receipt_time)::numeric, 1),
                   coalesce(e.apply_error_count, 0)
            FROM pg_stat_subscription s
            LEFT JOIN pg_stat_subscription_stats e ON e.subid = s.subid
            WHERE s.relid IS NULL ORDER BY 1""")  # relid NULL = proceso principal (no copia inicial)
        for nombre, segundos, errores in cursor.fetchall():
            print(f"  {nodo:<11} <- {nombre:<24} último mensaje hace {segundos} s   "
                  f"errores acumulados={errores} (incluye caídas del publicador)")
        conexion.close()


def main():
    """Compara las 40 capas, muestra el resultado y termina con error si alguna es diferente."""
    resultados = comparar()
    if "--resumen" not in sys.argv:
        mostrar_tabla(resultados)
        mostrar_retrasos()
    diferentes = [f"{e}.{c}" for e, c, _, ok in resultados if not ok]
    print(f"\n{len(resultados) - len(diferentes)} capas OK, {len(diferentes)} DIFERENTES")
    if diferentes:
        print("Diferentes:", ", ".join(diferentes))
    sys.exit(1 if diferentes else 0)


if __name__ == "__main__":
    main()
