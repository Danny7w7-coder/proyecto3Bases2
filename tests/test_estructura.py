"""
Pruebas de las fases 1 y 2: nodos, estructura PostGIS y datos de ejemplo.
"""
import os
import sys

import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from comun import CAMPUS, NODOS, SRID, conectar  # noqa: E402
from cargar_datos import CAPAS, UBICACION  # noqa: E402

# Tipo de geometría esperado por capa
TIPOS = {
    "edificios": "POLYGON", "carreteras": "LINESTRING", "aceras": "LINESTRING",
    "parqueos": "POLYGON", "zonas_verdes": "POLYGON", "puntos_interes": "POINT",
    "iluminacion": "POINT", "accesibilidad": "LINESTRING",
}


def consultar(nodo, sql, parametros=None):
    """Ejecuta una consulta y devuelve todas las filas."""
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    cursor.execute(sql, parametros)
    filas = cursor.fetchall()
    conexion.close()
    return filas


def prueba_nodos_postgis():
    """Los 6 nodos responden y tienen PostGIS"""
    for nodo in NODOS:
        filas = consultar(nodo, "SELECT postgis_lib_version()")
        assert filas, f"{nodo} sin PostGIS"
    return "6 nodos"


def prueba_capas_srid():
    """Cada nodo tiene 5 esquemas x 8 capas con el tipo y SRID correctos"""
    for nodo in NODOS:
        filas = consultar(nodo, """
            SELECT f_table_schema, f_table_name, type, srid
            FROM geometry_columns
            WHERE f_table_schema IN (SELECT esquema FROM public.campus)""")
        assert len(filas) == 40, f"{nodo}: {len(filas)} capas, se esperaban 40"
        for esquema, tabla, tipo, srid in filas:
            assert srid == SRID, f"{nodo} {esquema}.{tabla}: SRID {srid}"
            assert tipo == TIPOS[tabla], f"{nodo} {esquema}.{tabla}: tipo {tipo}"
    return f"40 capas por nodo, SRID {SRID}"


def prueba_indices_gist():
    """Cada capa tiene índice GIST sobre geom"""
    for nodo in NODOS:
        filas = consultar(nodo, """
            SELECT count(*) FROM pg_indexes
            WHERE schemaname IN (SELECT esquema FROM public.campus)
              AND indexdef ILIKE '%USING gist (geom)%'""")
        assert filas[0][0] == 40, f"{nodo}: {filas[0][0]} índices GIST"
    return "40 por nodo"


def prueba_config_mi_campus():
    """Cada nodo sabe quién es (config / mi_campus())"""
    for nodo, datos in NODOS.items():
        filas = consultar(nodo, "SELECT nodo, public.mi_campus() FROM public.config")
        assert filas == [(nodo, datos["campus_id"])], f"{nodo}: {filas}"


def prueba_datos_ejemplo():
    """Cada campus tiene entre 5 y 10 objetos por capa en su esquema"""
    for _, esquema in CAMPUS:
        for capa in CAPAS:
            total = consultar(esquema, f"SELECT count(*) FROM {esquema}.{capa}")[0][0]
            assert 5 <= total <= 10, f"{esquema}.{capa}: {total} filas"


def prueba_geometrias_validas():
    """Todas las geometrías de ejemplo son válidas (ST_IsValid)"""
    for _, esquema in CAMPUS:
        for capa in CAPAS:
            invalidas = consultar(esquema, f"SELECT count(*) FROM {esquema}.{capa} WHERE NOT ST_IsValid(geom)")[0][0]
            assert invalidas == 0, f"{esquema}.{capa}: {invalidas} inválidas"


def prueba_ids_globales():
    """Los ids están en el rango del campus y no se repiten entre capas"""
    for campus_id, esquema in CAMPUS:
        union = " UNION ALL ".join(f"SELECT id FROM {esquema}.{c}" for c in CAPAS)
        minimo, maximo, total, distintos = consultar(
            esquema, f"SELECT min(id), max(id), count(*), count(DISTINCT id) FROM ({union}) t")[0]
        assert campus_id * 1_000_000 < minimo and maximo < (campus_id + 1) * 1_000_000, \
            f"{esquema}: ids fuera de rango {minimo}..{maximo}"
        assert total == distintos, f"{esquema}: ids repetidos"


def prueba_ejemplo_enunciado():
    """Existen los edificios del ejemplo del enunciado con su área"""
    esperados = [("cartago", "Biblioteca", 1200), ("cartago", "Escuela de Computación", 850),
                 ("alajuela", "Edificio Académico", 600), ("san_carlos", "Laboratorios", 450)]
    for esquema, nombre, area in esperados:
        filas = consultar(esquema,
                          f"SELECT area, round(ST_Area(geom)) FROM {esquema}.edificios WHERE nombre = %s",
                          (nombre,))
        assert filas, f"falta {nombre} en {esquema}"
        assert filas[0][0] == area and filas[0][1] == area, f"{nombre}: área {filas[0]}"


def prueba_ubicacion_campus():
    """Los datos de cada campus caen cerca de su ubicación real (< 1 km)"""
    for _, esquema in CAMPUS:
        lat, lon = UBICACION[esquema]
        distancia = consultar(esquema, f"""
            SELECT ST_Distance(
                ST_Centroid(ST_Collect(geom)),
                ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s))
            FROM {esquema}.edificios""", (lon, lat, SRID))[0][0]
        assert distancia < 1000, f"{esquema}: a {distancia:.0f} m del campus"


def prueba_check_campus_dueno():
    """El CHECK rechaza una fila con campus_id distinto al dueño del esquema"""
    conexion = conectar("cartago", autocommit=False)
    cursor = conexion.cursor()
    try:
        cursor.execute(f"""
            INSERT INTO cartago.puntos_interes (campus_id, nombre, tipo, geom)
            VALUES (3, 'Intruso', 'otro', ST_SetSRID(ST_MakePoint(500000, 1090000), {SRID}))""")
        raise AssertionError("se aceptó campus_id = 3 en el esquema cartago")
    except psycopg2.errors.CheckViolation:
        return "rechazado"
    finally:
        conexion.rollback()
        conexion.close()


PRUEBAS = [
    prueba_nodos_postgis,
    prueba_capas_srid,
    prueba_indices_gist,
    prueba_config_mi_campus,
    prueba_datos_ejemplo,
    prueba_geometrias_validas,
    prueba_ids_globales,
    prueba_ejemplo_enunciado,
    prueba_ubicacion_campus,
    prueba_check_campus_dueno,
]
