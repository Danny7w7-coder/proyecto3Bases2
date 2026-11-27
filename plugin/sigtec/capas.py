"""
Carga de las 8 vistas del campus en el proyecto de QGIS.

Para cada capa:
  1. Se arma la conexión con QgsDataSourceUri (proveedor "postgres"):
     esquema sig, vista, columna geom, clave id, SRID y tipo de geometría.
     (Las vistas exponen geom sin tipo ni SRID, por eso se le indican a QGIS aquí.)
  2. Se crea la capa y se agrega al proyecto dentro de un grupo "SIG-TEC - <campus>".
  3. Se aplica el estilo vigente de layer_styles.
  4. Se conecta la señal de error: si la base rechaza una edición (por ejemplo,
     un objeto de otro campus), se muestra el mensaje del trigger en español.
"""
from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsDataSourceUri, QgsProject,
                       QgsRectangle, QgsVectorLayer)
from qgis.PyQt.QtXml import QDomDocument

from .logica import CAPAS, COLUMNA_CLAVE, COLUMNA_GEOMETRIA, ESQUEMA_VISTAS, limpiar_error

# Tipos de geometría de QGIS (Qgis.WkbType existe desde QGIS 3.30 y en QGIS 4)
try:
    _WKB = Qgis.WkbType
except AttributeError:  # QGIS anterior a 3.30
    from qgis.core import QgsWkbTypes as _WKB

TIPOS = {
    "Point": _WKB.Point,
    "LineString": _WKB.LineString,
    "Polygon": _WKB.Polygon,
}

PREFIJO_GRUPO = "SIG-TEC"


def uri_capa(datos, vista, tipo, srid):
    """Arma la URI de una vista del nodo del campus (datos = resultado de autenticar)."""
    uri = QgsDataSourceUri()
    uri.setConnection(datos["host"], str(datos["puerto"]), datos["base"],
                      datos["usuario_conexion"], datos["clave_conexion"])
    uri.setDataSource(ESQUEMA_VISTAS, vista, COLUMNA_GEOMETRIA, "", COLUMNA_CLAVE)
    uri.setSrid(str(srid))
    uri.setWkbType(TIPOS[tipo])
    return uri


def aplicar_estilo(capa, qml):
    """Aplica un estilo QML (texto) a la capa. Devuelve True si se aplicó."""
    if not qml:
        return False
    documento = QDomDocument()
    if not documento.setContent(qml):
        return False
    ok, _mensaje = capa.importNamedStyle(documento)
    capa.triggerRepaint()
    return ok


def quitar_grupo_anterior(proyecto):
    """Si ya se había entrado antes, quita el grupo SIG-TEC anterior (y sus capas)."""
    raiz = proyecto.layerTreeRoot()
    for grupo in list(raiz.children()):
        if grupo.name().startswith(PREFIJO_GRUPO):
            for hoja in grupo.findLayers():
                proyecto.removeMapLayer(hoja.layerId())
            raiz.removeChildNode(grupo)


def cargar_capas(datos, srid, estilos, al_fallar_edicion=None, proyecto=None):
    """Agrega las 8 capas al proyecto. Devuelve (lista de capas, lista de problemas).

    datos:  resultado de autenticar() (host, puerto, base, usuario y clave del nodo)
    estilos: {vista: qml} con los estilos vigentes
    al_fallar_edicion: función(nombre_capa, mensaje) que se llama si la base rechaza una edición
    """
    # Si el usuario ya había ingresado antes, se quitan las capas viejas
    proyecto = proyecto or QgsProject.instance()
    quitar_grupo_anterior(proyecto)
    # El mapa usa el sistema de coordenadas institucional (CRTM05)
    proyecto.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{srid}"))

    # Grupo arriba de todo en el panel de capas, con el nombre del campus
    grupo = proyecto.layerTreeRoot().insertGroup(0, f"{PREFIJO_GRUPO} - {datos['campus_nombre']}")
    capas, problemas = [], []

    for vista, nombre, tipo in CAPAS:
        # Cada capa lee la vista sig.<capa> del nodo del campus
        capa = QgsVectorLayer(uri_capa(datos, vista, tipo, srid).uri(False), nombre, "postgres")
        # Si una capa falla, se anota el problema y se sigue con las demás
        if not capa.isValid():
            problemas.append(f"{nombre}: no se pudo cargar ({capa.error().summary()})")
            continue
        # Estilo vigente que viene de layer_styles del central
        aplicar_estilo(capa, estilos.get(vista))
        # Para mostrar en QGIS el mensaje del trigger cuando se rechaza una edición
        if al_fallar_edicion:
            conectar_errores(capa, al_fallar_edicion)
        proyecto.addMapLayer(capa, False)  # False: no la agrega a la raíz, sino al grupo
        grupo.addLayer(capa)
        capas.append(capa)
    return capas, problemas


def conectar_errores(capa, al_fallar_edicion):
    """Cuando la base rechaza un cambio, QGIS emite raiseError con el texto del error."""
    nombre = capa.name()
    capa.raiseError.connect(lambda texto: al_fallar_edicion(nombre, limpiar_error(texto)))


def rectangulo(extension):
    """Convierte (xmin, ymin, xmax, ymax) en un QgsRectangle con un margen del 10 %."""
    if not extension:
        return None
    rect = QgsRectangle(*extension)
    rect.scale(1.1)
    return rect
