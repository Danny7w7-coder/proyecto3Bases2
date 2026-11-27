"""
Genera los estilos QGIS (QML) de las 8 capas y los publica en layer_styles del CENTRAL.
Desde ahí llegan a los 5 campus por replicación lógica (nivel 2).

Uso:
    python scripts/generar_estilos.py                          # publica la versión 1 de las capas que no tienen estilo
    python scripts/generar_estilos.py listar                   # muestra las versiones en el central
    python scripts/generar_estilos.py nueva edificios 70,130,200   # nueva versión de una capa con otro color
    python scripts/generar_estilos.py activar edificios 1      # vuelve a una versión anterior

El QML es el formato de estilos de QGIS 3 (XML). Aquí se arma con texto simple:
    - capas de polígonos y líneas: un solo símbolo (color y grosor)
    - puntos de interés: un color por tipo (cajero, soda, laboratorio, ...)
    - iluminación: un color por estado (funcionando, dañada, mantenimiento)
    - edificios: además muestran el nombre como etiqueta
"""
import sys

from comun import conectar

# ---------------------------------------------------------------------
# Piezas del QML
# ---------------------------------------------------------------------
def opciones(valores):
    """Bloque <Option type="Map"> con las propiedades de una capa de símbolo."""
    lineas = "".join(f'<Option name="{k}" type="QString" value="{v}"/>' for k, v in valores.items())
    return f'<Option type="Map">{lineas}</Option>'


def simbolo(nombre, tipo, clase, valores):
    """Un símbolo de QGIS: tipo = fill / line / marker. clase = SimpleFill / SimpleLine / SimpleMarker."""
    return (f'<symbol name="{nombre}" type="{tipo}" alpha="1" clip_to_extent="1" force_rhr="0">'
            f'<layer class="{clase}" enabled="1" locked="0" pass="0">{opciones(valores)}</layer>'
            f'</symbol>')


def relleno(color, borde, nombre="0"):
    """Símbolo de polígono con color de relleno y de borde."""
    return simbolo(nombre, "fill", "SimpleFill", {
        "color": f"{color},255", "outline_color": f"{borde},255", "outline_width": "0.4",
        "outline_width_unit": "MM", "style": "solid", "outline_style": "solid", "joinstyle": "bevel"})


def linea(color, ancho, estilo="solid", nombre="0"):
    """Símbolo de línea con color, grosor y tipo de trazo."""
    return simbolo(nombre, "line", "SimpleLine", {
        "line_color": f"{color},255", "line_width": str(ancho), "line_width_unit": "MM",
        "line_style": estilo, "capstyle": "round", "joinstyle": "round"})


def marcador(color, forma="circle", tamano=3, nombre="0"):
    """Símbolo de punto con forma, color y tamaño."""
    return simbolo(nombre, "marker", "SimpleMarker", {
        "name": forma, "color": f"{color},255", "outline_color": "50,50,50,255",
        "outline_width": "0.2", "outline_width_unit": "MM", "size": str(tamano), "size_unit": "MM"})


def renderer_simple(sim):
    """Renderer de QGIS con un solo símbolo para toda la capa."""
    return (f'<renderer-v2 type="singleSymbol" forceraster="0" symbollevels="0" enableorderby="0">'
            f'<symbols>{sim}</symbols></renderer-v2>')


def renderer_categorias(campo, categorias, forma):
    """categorias: lista de (valor, etiqueta, color). Un símbolo por categoría."""
    cats = "".join(f'<category render="true" value="{v}" symbol="{i}" label="{e}"/>'
                   for i, (v, e, _) in enumerate(categorias))
    sims = "".join(marcador(c, forma, nombre=str(i)) for i, (_, _, c) in enumerate(categorias))
    return (f'<renderer-v2 type="categorizedSymbol" attr="{campo}" forceraster="0" symbollevels="0" '
            f'enableorderby="0"><categories>{cats}</categories><symbols>{sims}</symbols></renderer-v2>')


def etiquetas(campo):
    """Etiquetas simples con el valor de un campo y un borde blanco para que se lean."""
    return (f'<labeling type="simple"><settings calloutType="simple">'
            f'<text-style fieldName="{campo}" isExpression="0" fontFamily="Arial" fontSize="8" '
            f'fontSizeUnit="Point" textColor="40,40,40,255" textOpacity="1">'
            f'<text-buffer bufferDraw="1" bufferSize="0.8" bufferSizeUnits="MM" bufferColor="255,255,255,255"/>'
            f'</text-style><placement placement="1"/><rendering scaleVisibility="0"/>'
            f'</settings></labeling>')


def qml(renderer, labeling=""):
    """Documento QML completo (raíz <qgis>) con el renderer y, si hay, las etiquetas."""
    con_etiquetas = "1" if labeling else "0"
    return (f'<qgis version="3.34.0" styleCategories="Symbology|Labeling" labelsEnabled="{con_etiquetas}">'
            f'{renderer}{labeling}</qgis>')


# ---------------------------------------------------------------------
# Estilo de cada capa: (tipo de geometría para layer_styles, función que arma el QML)
# El parámetro "color" permite crear otra versión con un color distinto.
# ---------------------------------------------------------------------
ESTILOS = {
    "edificios":      ("Polygon", "205,170,125",
                       lambda c: qml(renderer_simple(relleno(c, "120,85,50")), etiquetas("nombre"))),
    "parqueos":       ("Polygon", "170,170,170",
                       lambda c: qml(renderer_simple(relleno(c, "90,90,90")))),
    "zonas_verdes":   ("Polygon", "130,195,105",
                       lambda c: qml(renderer_simple(relleno(c, "60,130,50")))),
    "carreteras":     ("Line", "90,90,90",
                       lambda c: qml(renderer_simple(linea(c, 1.6)))),
    "aceras":         ("Line", "215,185,140",
                       lambda c: qml(renderer_simple(linea(c, 0.8)))),
    "accesibilidad":  ("Line", "30,110,220",
                       lambda c: qml(renderer_simple(linea(c, 1.2, "dash")))),
    "puntos_interes": ("Point", None,
                       lambda c: qml(renderer_categorias("tipo", [
                           ("cajero", "Cajero", "40,160,80"),
                           ("laboratorio", "Laboratorio", "140,80,190"),
                           ("soda", "Soda", "240,140,30"),
                           ("biblioteca", "Biblioteca", "40,100,200"),
                           ("parada_bus", "Parada de bus", "230,200,30"),
                           ("otro", "Otro", "150,150,150")], "circle"))),
    "iluminacion":    ("Point", None,
                       lambda c: qml(renderer_categorias("estado", [
                           ("funcionando", "Funcionando", "255,220,0"),
                           ("danada", "Dañada", "220,40,40"),
                           ("mantenimiento", "Mantenimiento", "240,140,30")], "star"))),
}


def publicar(capa, color=None, descripcion="Estilo institucional SIG-TEC"):
    """Crea una nueva versión del estilo de una capa en el central y la deja vigente. Devuelve el número de versión."""
    tipo, color_base, armar = ESTILOS[capa]
    texto_qml = armar(color or color_base)
    conexion = conectar("central")
    cursor = conexion.cursor()
    cursor.execute("SELECT public.publicar_estilo(%s, %s, %s, %s)", (capa, texto_qml, descripcion, tipo))
    version = cursor.fetchone()[0]
    conexion.close()
    print(f"  [central] sig.{capa}: versión {version} publicada y vigente")
    return version


def publicar_faltantes():
    """Publica la versión 1 de las capas que todavía no tienen estilo."""
    conexion = conectar("central")
    cursor = conexion.cursor()
    cursor.execute("SELECT DISTINCT f_table_name FROM public.layer_styles WHERE f_table_schema = 'sig'")
    con_estilo = {fila[0] for fila in cursor.fetchall()}
    conexion.close()
    for capa in ESTILOS:
        if capa in con_estilo:
            print(f"  [central] sig.{capa}: ya tiene estilo")
        else:
            publicar(capa)


def listar():
    """Muestra todas las versiones de los estilos guardadas en el central."""
    conexion = conectar("central")
    cursor = conexion.cursor()
    cursor.execute("""SELECT f_table_name, version, vigente, update_time::timestamp(0), description
                      FROM public.layer_styles ORDER BY f_table_name, version""")
    for capa, version, vigente, fecha, descripcion in cursor.fetchall():
        print(f"  {capa:<15} v{version:<3} {'VIGENTE' if vigente else '       '}  {fecha}  {descripcion}")
    conexion.close()


def activar(capa, version):
    """Vuelve a dejar vigente una versión anterior del estilo de una capa."""
    conexion = conectar("central")
    conexion.cursor().execute("SELECT public.activar_version_estilo(%s, %s)", (capa, version))
    conexion.close()
    print(f"  [central] sig.{capa}: versión {version} vigente de nuevo")


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "faltantes"
    if accion == "listar":
        listar()
    elif accion == "nueva":
        publicar(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None, "Nueva versión del estilo")
    elif accion == "activar":
        activar(sys.argv[2], int(sys.argv[3]))
    else:
        publicar_faltantes()
