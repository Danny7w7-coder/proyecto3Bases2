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


RUTA_ENV = os.path.join(RAIZ, ".env")
RUTA_PLANTILLA = os.path.join(RAIZ, ".env.example")
# Claves que se generan al azar en cada instalación (en la plantilla están vacías)
CLAVES_ALEATORIAS = ["DB_PASSWORD", "REPL_PASSWORD", "EDITOR_PASSWORD"]


def crear_env():
    """Crea .env a partir de .env.example y llena las claves vacías con valores aleatorios.
    Solo pasa la primera vez: si .env ya existe no se toca (los nodos ya usan esas claves)."""
    import secrets
    lineas = []
    with open(RUTA_PLANTILLA, encoding="utf-8") as plantilla:
        for linea in plantilla:
            clave = linea.split("=", 1)[0].strip()
            if clave in CLAVES_ALEATORIAS and linea.strip() == clave + "=":
                linea = f"{clave}={secrets.token_hex(16)}\n"  # 32 caracteres 0-9a-f
            lineas.append(linea)
    with open(RUTA_ENV, "w", encoding="utf-8") as archivo:
        archivo.writelines(lineas)
    print("Se creó .env con claves aleatorias (no se sube a git).")


def leer_env():
    """Lee el archivo .env y devuelve un diccionario {clave: valor}. Si no existe, lo crea."""
    if not os.path.exists(RUTA_ENV):
        crear_env()
    valores = {}
    ruta = RUTA_ENV
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


def conectar(nodo, autocommit=True, usuario=None, clave=None):
    """Abre una conexión al nodo indicado desde la máquina anfitriona.
    Por defecto entra como superusuario. Se puede indicar otro usuario y clave."""
    conexion = psycopg2.connect(
        host="127.0.0.1",
        port=NODOS[nodo]["puerto"],
        dbname=ENV["DB_NAME"],
        user=usuario or ENV["DB_USER"],
        password=clave or ENV["DB_PASSWORD"],
        connect_timeout=3,
    )
    conexion.autocommit = autocommit
    return conexion


def contar(nodo, sql, parametros=None):
    """Ejecuta un SELECT count(*) (o cualquier valor único) en el nodo y lo devuelve."""
    conexion = conectar(nodo)
    cursor = conexion.cursor()
    cursor.execute(sql, parametros)
    valor = cursor.fetchone()[0]
    conexion.close()
    return valor


def esperar_hasta(condicion, segundos=20):
    """Repite condicion() cada 0.2 s hasta que sea verdadera. Devuelve los segundos que tardó."""
    inicio = time.time()
    while time.time() - inicio < segundos:
        if condicion():
            return round(time.time() - inicio, 2)
        time.sleep(0.2)
    raise TimeoutError(f"no se cumplió en {segundos} s")


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
