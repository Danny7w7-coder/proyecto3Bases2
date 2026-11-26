"""
Muestra el estado de los 6 nodos: si responden, versión de PostgreSQL y PostGIS,
y los parámetros que necesita el proyecto (replicación lógica, 2PC y WAL).

Uso: python scripts/estado_nodos.py
"""
from comun import NODOS, conectar, revisar_servidores_de_esta_carpeta

# Parámetros a revisar y el valor esperado (None = solo mostrar)
PARAMETROS = {
    "wal_level": "logical",
    "max_prepared_transactions": "20",
    "archive_mode": "on",
    "max_replication_slots": "20",
}


def estado(nodo):
    """Devuelve una lista con los datos de un nodo, o None si no responde."""
    try:
        conexion = conectar(nodo)
    except Exception:
        return None
    cursor = conexion.cursor()
    cursor.execute("SHOW server_version")
    version_pg = cursor.fetchone()[0].split()[0]
    cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
    fila = cursor.fetchone()
    version_postgis = fila[0] if fila else "NO"
    cursor.execute("SELECT count(*) FROM pg_extension WHERE extname = 'pgcrypto'")
    pgcrypto = "si" if cursor.fetchone()[0] else "no"
    valores = []
    for parametro in PARAMETROS:
        cursor.execute(f"SHOW {parametro}")
        valores.append(cursor.fetchone()[0])
    # Cuántos WAL se han archivado bien
    cursor.execute("SELECT archived_count, failed_count FROM pg_stat_archiver")
    archivados, fallidos = cursor.fetchone()
    conexion.close()
    return [version_pg, version_postgis, pgcrypto, *valores, f"{archivados}/{fallidos}"]


def main():
    problema = revisar_servidores_de_esta_carpeta()
    if problema:
        print(f"AVISO: {problema}\n")
    titulos = ["nodo", "pg", "postgis", "pgcrypto", *PARAMETROS, "wal ok/fallo", "estado"]
    filas = []
    todo_ok = True
    for nodo in NODOS:
        datos = estado(nodo)
        if datos is None:
            filas.append([nodo] + ["-"] * (len(titulos) - 2) + ["CAIDO"])
            todo_ok = False
            continue
        # Revisar que los parámetros tengan el valor esperado
        ok = datos[1] != "NO"
        for i, esperado in enumerate(PARAMETROS.values()):
            if datos[3 + i] != esperado:
                ok = False
        todo_ok = todo_ok and ok
        filas.append([nodo, *datos, "OK" if ok else "REVISAR"])

    # Imprimir la tabla con columnas alineadas
    anchos = [max(len(str(f[i])) for f in filas + [titulos]) for i in range(len(titulos))]
    print("  ".join(t.ljust(a) for t, a in zip(titulos, anchos)))
    for fila in filas:
        print("  ".join(str(v).ljust(a) for v, a in zip(fila, anchos)))
    print("\nTODO OK" if todo_ok else "\nHAY NODOS CON PROBLEMAS")


if __name__ == "__main__":
    main()
