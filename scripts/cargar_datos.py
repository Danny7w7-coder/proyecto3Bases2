"""
Carga datos de ejemplo en cada campus (solo en SU propio esquema, en SU nodo).
Los otros nodos reciben estos datos por replicación lógica (fase 3).

Cómo se arman las geometrías:
  1. Se toma la ubicación aproximada del campus en lat/lon (EPSG:4326).
  2. PostGIS la convierte al SRID institucional con ST_Transform -> centro (x, y) en metros.
  3. Cada objeto se dibuja con desplazamientos en metros alrededor de ese centro.

Uso:
    python scripts/cargar_datos.py            # carga solo en los campus que estén vacíos
    python scripts/cargar_datos.py --forzar   # borra los datos de ejemplo y los vuelve a cargar
"""
import sys

from comun import CAMPUS, SRID, conectar

# Ubicación aproximada de cada campus (latitud, longitud en EPSG:4326)
UBICACION = {
    "cartago":    (9.8557, -83.9125),
    "san_jose":   (9.9378, -84.0743),
    "san_carlos": (10.3606, -84.5116),
    "alajuela":   (10.0193, -84.2139),
    "limon":      (9.9902, -83.0322),
}

CAPAS = ["edificios", "carreteras", "aceras", "parqueos",
         "zonas_verdes", "puntos_interes", "iluminacion", "accesibilidad"]

# Edificios del ejemplo del enunciado (p.3): campus -> lista de (nombre, ancho, alto)
# El ancho x alto da exactamente el área del ejemplo.
EDIFICIOS_ENUNCIADO = {
    "cartago":    [("Biblioteca", 40, 30), ("Escuela de Computación", 34, 25)],   # 1200 y 850 m2
    "alajuela":   [("Edificio Académico", 30, 20)],                               # 600 m2
    "san_carlos": [("Laboratorios", 30, 15)],                                     # 450 m2
}
EDIFICIOS_GENERICOS = [("Aulas", 45, 25), ("Administración", 35, 20), ("Gimnasio", 50, 35),
                       ("Comedor", 30, 25), ("Auditorio", 40, 28), ("Residencias", 45, 20)]


# ---------------------------------------------------------------------
# Funciones para escribir geometrías en WKT (texto) a partir del centro
# ---------------------------------------------------------------------
def rectangulo(cx, cy, x, y, ancho, alto):
    """Polígono rectangular con esquina inferior izquierda en (cx+x, cy+y)."""
    x0, y0 = cx + x, cy + y
    x1, y1 = x0 + ancho, y0 + alto
    return f"POLYGON(({x0} {y0}, {x1} {y0}, {x1} {y1}, {x0} {y1}, {x0} {y0}))"


def linea(cx, cy, puntos):
    """LineString a partir de una lista de desplazamientos [(x, y), ...]."""
    texto = ", ".join(f"{cx + x} {cy + y}" for x, y in puntos)
    return f"LINESTRING({texto})"


def punto(cx, cy, x, y):
    return f"POINT({cx + x} {cy + y})"


# ---------------------------------------------------------------------
# Carga de un campus
# ---------------------------------------------------------------------
def insertar(cursor, esquema, tabla, columnas, valores, wkt):
    """Inserta una fila. La geometría se convierte desde WKT con el SRID institucional."""
    lista_columnas = ", ".join(columnas + ["geom"])
    marcas = ", ".join(["%s"] * len(columnas))
    sql = (f"INSERT INTO {esquema}.{tabla} ({lista_columnas}) "
           f"VALUES ({marcas}, ST_GeomFromText(%s, %s))")
    cursor.execute(sql, list(valores) + [wkt, SRID])


def cargar_campus(campus_id, esquema, forzar):
    conexion = conectar(esquema, autocommit=False)
    cursor = conexion.cursor()

    cursor.execute(f"SELECT count(*) FROM {esquema}.edificios")
    if cursor.fetchone()[0] > 0 and not forzar:
        print(f"  [{esquema}] ya tiene datos, se omite (use --forzar para recargar)")
        conexion.close()
        return

    if forzar:
        for capa in CAPAS:
            cursor.execute(f"DELETE FROM {esquema}.{capa}")
        cursor.execute(f"ALTER SEQUENCE {esquema}.seq_id RESTART")

    # Centro del campus convertido de lat/lon (4326) al SRID institucional
    lat, lon = UBICACION[esquema]
    cursor.execute(
        "SELECT ST_X(p), ST_Y(p) FROM ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s) AS p",
        (lon, lat, SRID))
    cx, cy = cursor.fetchone()
    cx, cy = round(cx, 2), round(cy, 2)
    n = campus_id  # se usa para variar un poco los datos entre campus

    # 1. Edificios: primero los del enunciado, luego genéricos hasta llegar a 6
    edificios = EDIFICIOS_ENUNCIADO.get(esquema, []) + EDIFICIOS_GENERICOS
    posiciones = [(-160, 20), (-90, 20), (-20, 20), (-160, 90), (-90, 90), (-20, 90)]
    for i, ((nombre, ancho, alto), (x, y)) in enumerate(zip(edificios, posiciones), start=1):
        codigo = f"{esquema[:3].upper()}-E{i:02d}"
        insertar(cursor, esquema, "edificios", ["nombre", "codigo", "area", "pisos"],
                 [nombre, codigo, ancho * alto, 1 + (i + n) % 4],
                 rectangulo(cx, cy, x, y, ancho, alto))

    # 2. Carreteras
    carreteras = [
        ("Calle principal", "principal", "asfalto", [(-250, 0), (250, 0)]),
        ("Calle sur", "secundaria", "asfalto", [(-250, -60), (100, -60)]),
        ("Acceso oeste", "interna", "concreto", [(-200, -150), (-200, 150)]),
        ("Acceso este", "interna", "lastre", [(120, -150), (120, 0), (130, 150)]),
        ("Calle de servicio", "servicio", "adoquin", [(230, -150), (230, 160)]),
    ]
    for nombre, tipo, superficie, puntos in carreteras:
        insertar(cursor, esquema, "carreteras", ["nombre", "tipo", "superficie"],
                 [nombre, tipo, superficie], linea(cx, cy, puntos))

    # 3. Aceras (paralelas a las calles, a unos metros)
    aceras = [
        ("concreto", 2.0, "buena", [(-250, 8), (250, 8)]),
        ("concreto", 2.0, "regular", [(-250, -8), (250, -8)]),
        ("adoquin", 1.5, "buena", [(-250, -52), (100, -52)]),
        ("concreto", 1.5, "mala", [(-192, -150), (-192, 150)]),
        ("asfalto", 1.2, "regular", [(112, -150), (112, -8)]),
        ("concreto", 2.5, "buena", [(-170, 15), (30, 15)]),
    ]
    for material, ancho, condicion, puntos in aceras:
        insertar(cursor, esquema, "aceras", ["material", "ancho", "condicion"],
                 [material, ancho, condicion], linea(cx, cy, puntos))

    # 4. Parqueos (columna al este)
    parqueos = [
        ("Parqueo estudiantes 1", 80, "estudiantes"),
        ("Parqueo estudiantes 2", 60, "estudiantes"),
        ("Parqueo funcionarios", 40, "funcionarios"),
        ("Parqueo visitantes", 20, "visitantes"),
        ("Parqueo motos", 30, "motos"),
    ]
    alturas_y = [-150, -100, 20, 75, 130]  # dejan libre la calle principal (y = 0)
    for i, ((nombre, capacidad, tipo), y) in enumerate(zip(parqueos, alturas_y)):
        disponibles = (capacidad * (i + n)) // 7 % (capacidad + 1)
        insertar(cursor, esquema, "parqueos", ["nombre", "capacidad", "tipo", "disponibilidad"],
                 [nombre, capacidad, tipo, disponibles],
                 rectangulo(cx, cy, 150, y, 50, 40))

    # 5. Zonas verdes (fila al sur)
    zonas = [("Plaza central", "cesped"), ("Jardín botánico", "jardin"),
             ("Arboleda", "arboles"), ("Bosque", "bosque"), ("Zona de descanso", "mixta")]
    for i, (nombre, vegetacion) in enumerate(zonas):
        ancho, alto = 50, 40 + i * 5
        insertar(cursor, esquema, "zonas_verdes", ["nombre", "area", "tipo_vegetacion"],
                 [nombre, ancho * alto, vegetacion],
                 rectangulo(cx, cy, -190 + i * 60, -140, ancho, alto))

    # 6. Puntos de interés
    puntos_interes = [
        ("Cajero BCR", "cajero", "Cajero automático", -110, 12),
        ("Laboratorio de cómputo", "laboratorio", "Laboratorio general", -70, 55),
        ("Soda central", "soda", "Comidas y bebidas", -5, 55),
        ("Biblioteca (entrada)", "biblioteca", "Préstamo de libros", -140, 55),
        ("Parada de bus", "parada_bus", "Buses al centro", 60, 12),
        ("Laboratorio de química", "laboratorio", "Laboratorio de ciencias", -140, 120),
        ("Soda norte", "soda", "Café y repostería", 0, 125),
    ]
    for nombre, tipo, descripcion, x, y in puntos_interes:
        insertar(cursor, esquema, "puntos_interes", ["nombre", "tipo", "descripcion"],
                 [nombre, tipo, descripcion], punto(cx, cy, x, y))

    # 7. Iluminación (postes a lo largo de la calle principal)
    estados = ["funcionando", "funcionando", "funcionando", "danada", "mantenimiento"]
    for i in range(8):
        codigo = f"L-{n}-{i + 1:03d}"
        insertar(cursor, esquema, "iluminacion", ["codigo", "potencia", "estado"],
                 [codigo, 100 + 50 * (i % 3), estados[(i + n) % len(estados)]],
                 punto(cx, cy, -210 + i * 60, 10))

    # 8. Accesibilidad (rampas y pasos cerca de las entradas)
    accesos = [
        ("rampa", "Rampa entrada aulas", [(-140, 15), (-140, 20)]),
        ("rampa", "Rampa biblioteca", [(-70, 15), (-70, 20)]),
        ("paso_accesible", "Paso peatonal calle principal", [(-30, -8), (-30, 8)]),
        ("ruta_podotactil", "Ruta podotáctil a la soda", [(-170, 15), (-5, 15), (-5, 55)]),
        ("paso_accesible", "Paso a parqueos", [(112, -20), (150, -20)]),
    ]
    for tipo, descripcion, puntos in accesos:
        insertar(cursor, esquema, "accesibilidad", ["tipo", "descripcion"],
                 [tipo, descripcion], linea(cx, cy, puntos))

    conexion.commit()  # todo el campus en una sola transacción
    cursor.execute(" UNION ALL ".join(f"SELECT count(*) FROM {esquema}.{c}" for c in CAPAS))
    total = sum(fila[0] for fila in cursor.fetchall())
    print(f"  [{esquema}] {total} objetos cargados")
    conexion.close()


def main():
    forzar = "--forzar" in sys.argv
    for campus_id, esquema in CAMPUS:
        cargar_campus(campus_id, esquema, forzar)


if __name__ == "__main__":
    main()
