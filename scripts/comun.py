"""
Funciones comunes para todos los scripts de SIG-TEC.

- Lee el archivo .env
- Define la lista de nodos (central + 5 campus)
- Da una función para conectarse a cualquier nodo
"""
import os
import time

import psycopg2

# Carpeta raíz del proyecto (sig-tec/)
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def leer_env():
    """Lee el archivo .env y devuelve un diccionario {clave: valor}."""
    valores = {}
    ruta = os.path.join(RAIZ, ".env")
    with open(ruta, encoding="utf-8") as archivo:
        for linea in archivo:
            linea = linea.strip()
            # Saltar líneas vacías y comentarios
            if not linea or linea.startswith("#"):
                continue
            clave, valor = linea.split("=", 1)
            valores[clave.strip()] = valor.strip()
    return valores


ENV = leer_env()
SRID = int(ENV["SRID"])

# Los 5 campus: (campus_id, nombre del nodo / esquema)
CAMPUS = [
    (1, "cartago"),
    (2, "san_jose"),
    (3, "san_carlos"),
    (4, "alajuela"),
    (5, "limon"),
]

# Todos los nodos: nombre -> datos. El central no tiene campus_id.
NODOS = {"central": {"campus_id": None, "puerto": int(ENV["PORT_CENTRAL"])}}
for campus_id, nombre in CAMPUS:
    NODOS[nombre] = {
        "campus_id": campus_id,
        "puerto": int(ENV["PORT_" + nombre.upper()]),
    }


def conectar(nodo, autocommit=True):
    """Abre una conexión al nodo indicado desde la máquina anfitriona."""
    conexion = psycopg2.connect(
        host="127.0.0.1",
        port=NODOS[nodo]["puerto"],
        dbname=ENV["DB_NAME"],
        user=ENV["DB_USER"],
        password=ENV["DB_PASSWORD"],
        connect_timeout=3,
    )
    conexion.autocommit = autocommit
    return conexion


def esperar_nodo(nodo, segundos=90):
    """Intenta conectarse al nodo hasta que responda o se acabe el tiempo."""
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            conexion = conectar(nodo)
            conexion.close()
            return True
        except psycopg2.OperationalError:
            time.sleep(2)
    return False
