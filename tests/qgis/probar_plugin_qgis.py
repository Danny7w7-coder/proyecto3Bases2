"""
Prueba de punta a punta del plugin DENTRO de QGIS (sin abrir la ventana principal).
Se ejecuta con el Python de QGIS, no con el Python normal:

    "C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" tests/qgis/probar_plugin_qgis.py

La corre automáticamente tests/test_plugin_qgis.py. Imprime una línea OK / FALLO por prueba.
"""
import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # sin pantalla

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "plugin"))

from qgis.core import QgsApplication, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsProject  # noqa: E402
from qgis.gui import QgsMapCanvas  # noqa: E402

app = QgsApplication([], True)
app.initQgis()

import sigtec  # noqa: E402
from sigtec import logica  # noqa: E402
from sigtec.dialogo_login import DialogoLogin  # noqa: E402

resultados = []


def prueba(nombre):
    """Decorador: corre la función y anota OK o FALLO."""
    def decorar(funcion):
        """Ejecuta la función decorada y anota OK o FALLO con su detalle."""
        try:
            detalle = funcion()
            resultados.append(True)
            print(f"OK     {nombre}" + (f"  ({detalle})" if detalle else ""), flush=True)
        except Exception as error:  # noqa: BLE001
            resultados.append(False)
            print(f"FALLO  {nombre}\n       -> {error}", flush=True)
            traceback.print_exc()
        return funcion
    return decorar


class BarraMensajes:
    def __init__(self):
        """Lista donde se guardan los mensajes que muestra el plugin."""
        self.mensajes = []

    def pushMessage(self, titulo, texto, level=None, duration=None):
        """Guarda el mensaje en lugar de mostrarlo (imita iface.messageBar())."""
        self.mensajes.append((titulo, texto))


class IfaceDePrueba:
    """Imita lo poco que el plugin usa de 'iface' (la interfaz de QGIS)."""
    def __init__(self):
        """Crea un mapa real de QGIS y una barra de mensajes de prueba."""
        self.lienzo = QgsMapCanvas()
        self.barra = BarraMensajes()
        self.acciones = []

    def mainWindow(self):
        """En la prueba no hay ventana principal."""
        return None

    def addToolBarIcon(self, accion):
        """Guarda el botón que agrega el plugin."""
        self.acciones.append(accion)

    def addPluginToMenu(self, menu, accion):
        """El menú no se revisa en esta prueba."""
        pass

    def removePluginMenu(self, menu, accion):
        """El menú no se revisa en esta prueba."""
        pass

    def removeToolBarIcon(self, accion):
        """Quita el botón guardado."""
        self.acciones.remove(accion)

    def mapCanvas(self):
        """Devuelve el mapa de prueba."""
        return self.lienzo

    def messageBar(self):
        """Devuelve la barra de mensajes de prueba."""
        return self.barra


iface = IfaceDePrueba()
plugin = sigtec.classFactory(iface)
estado = {}


def capa(nombre):
    """Devuelve la capa del proyecto que tiene ese nombre."""
    return QgsProject.instance().mapLayersByName(nombre)[0]


# ---------------------------------------------------------------------
@prueba("El plugin se carga en QGIS y agrega su botón (initGui)")
def _():
    """Paso: El plugin se carga en QGIS y agrega su botón (initGui)."""
    plugin.initGui()
    assert len(iface.acciones) == 1
    return iface.acciones[0].text()


@prueba("Ventana de login: clave mala muestra el error y no cierra")
def _():
    """Paso: Ventana de login: clave mala muestra el error y no cierra."""
    dialogo = DialogoLogin(plugin.ingresar)
    dialogo.usuario.setText("sancarlos1")
    dialogo.clave.setText("mala")
    dialogo.boton_ingresar.click()
    assert dialogo.result() == 0, "la ventana se cerró"
    assert "incorrectos" in dialogo.mensaje.text(), dialogo.mensaje.text()
    return dialogo.mensaje.text()


@prueba("Ventana de login: credenciales correctas cierran la ventana y cargan las 8 capas")
def _():
    """Paso: Ventana de login: credenciales correctas cierran la ventana y cargan las 8 capas."""
    dialogo = DialogoLogin(plugin.ingresar)
    dialogo.usuario.setText("sancarlos1")
    dialogo.clave.setText("tec2026")
    dialogo.boton_ingresar.click()
    assert dialogo.result() == 1, dialogo.mensaje.text()
    grupo = QgsProject.instance().layerTreeRoot().children()[0]
    nombres = [h.name() for h in grupo.findLayers()]
    assert len(nombres) == 8, nombres
    assert all(capa(n).isValid() for n in nombres)
    return f"grupo '{grupo.name()}'"


@prueba("Las capas tienen SRID 5367, clave id, datos de los 5 campus y su estilo")
def _():
    """Paso: Las capas tienen SRID 5367, clave id, datos de los 5 campus y su estilo."""
    resumen = []
    for vista, nombre, _ in logica.CAPAS:
        c = capa(nombre)
        assert c.crs().authid() == "EPSG:5367", f"{nombre}: {c.crs().authid()}"
        assert c.dataProvider().pkAttributeIndexes() == [c.fields().indexOf("id")], f"{nombre}: clave"
        campus = {f["campus_id"] for f in c.getFeatures()}
        assert campus == {1, 2, 3, 4, 5}, f"{nombre}: campus {campus}"
        resumen.append(c.renderer().type())
    assert capa("Puntos de interés").renderer().type() == "categorizedSymbol"
    assert capa("Edificios").labelsEnabled()
    return f"renderers: {sorted(set(resumen))}"


@prueba("El mapa queda centrado en el campus del usuario")
def _():
    """Paso: El mapa queda centrado en el campus del usuario."""
    centro = iface.mapCanvas().extent().center()
    rect = iface.mapCanvas().extent()
    pedido = QgsFeatureRequest().setFilterExpression('"campus_id" = 3')
    edificio = next(capa("Edificios").getFeatures(pedido))
    assert rect.contains(edificio.geometry().boundingBox()), "el campus no está en la vista"
    return f"centro ({round(centro.x())}, {round(centro.y())})"


@prueba("Editar un objeto PROPIO desde QGIS se guarda")
def _():
    """Paso: Editar un objeto PROPIO desde QGIS se guarda."""
    c = capa("Edificios")
    propio = next(c.getFeatures(QgsFeatureRequest().setFilterExpression('"campus_id" = 3')))
    estado["propio"] = (propio.id(), propio["pisos"])
    c.startEditing()
    c.changeAttributeValue(propio.id(), c.fields().indexOf("pisos"), 7)
    assert c.commitChanges(), c.commitErrors()
    assert next(c.getFeatures(QgsFeatureRequest(propio.id())))["pisos"] == 7
    # dejarlo como estaba
    c.startEditing()
    c.changeAttributeValue(propio.id(), c.fields().indexOf("pisos"), estado["propio"][1])
    assert c.commitChanges()
    return f"objeto {propio['id']}"


@prueba("Editar un objeto de OTRO campus se rechaza y el plugin muestra el mensaje")
def _():
    """Paso: Editar un objeto de OTRO campus se rechaza y el plugin muestra el mensaje."""
    c = capa("Edificios")
    ajeno = next(c.getFeatures(QgsFeatureRequest().setFilterExpression('"campus_id" = 1')))
    antes = len(iface.barra.mensajes)
    c.startEditing()
    c.changeAttributeValue(ajeno.id(), c.fields().indexOf("pisos"), 9)
    assert not c.commitChanges(), "QGIS guardó el cambio ajeno"
    c.rollBack()
    nuevos = [t for _, t in iface.barra.mensajes[antes:]]
    assert any("pertenece al Campus Tecnológico Central Cartago" in t for t in nuevos), nuevos
    return [t for t in nuevos if "pertenece" in t][0][:90] + "..."


@prueba("Borrar un objeto de OTRO campus se rechaza")
def _():
    """Paso: Borrar un objeto de OTRO campus se rechaza."""
    c = capa("Iluminación")
    ajeno = next(c.getFeatures(QgsFeatureRequest().setFilterExpression('"campus_id" = 2')))
    c.startEditing()
    c.deleteFeature(ajeno.id())
    assert not c.commitChanges(), "QGIS borró el objeto ajeno"
    c.rollBack()
    assert any(f.id() == ajeno.id() for f in c.getFeatures())


@prueba("Crear y borrar un objeto nuevo desde QGIS (queda en San Carlos con id de su rango)")
def _():
    """Paso: Crear y borrar un objeto nuevo desde QGIS (queda en San Carlos con id de su rango)."""
    c = capa("Puntos de interés")
    c.startEditing()
    nuevo = QgsFeature(c.fields())
    nuevo["nombre"] = "PRUEBA-QGIS"
    nuevo["tipo"] = "cajero"
    centro = iface.mapCanvas().extent().center()
    nuevo.setGeometry(QgsGeometry.fromPointXY(centro))
    assert c.addFeature(nuevo)
    assert c.commitChanges(), c.commitErrors()
    creado = next(c.getFeatures(QgsFeatureRequest().setFilterExpression("\"nombre\" = 'PRUEBA-QGIS'")))
    assert creado["campus_id"] == 3 and 3_000_000 < creado["id"] < 4_000_000, (creado["campus_id"], creado["id"])
    c.startEditing()
    c.deleteFeature(creado.id())
    assert c.commitChanges(), c.commitErrors()
    return f"id {creado['id']}"


@prueba("Respaldo sin psycopg2: el ejecutor de QGIS también autentica")
def _():
    """Paso: Respaldo sin psycopg2: el ejecutor de QGIS también autentica."""
    from sigtec.conexion_qgis import ejecutor_qgis
    config = logica.leer_config()["central"]
    ejecutar = ejecutor_qgis(config["host"], config["puerto"], config["base"], config["usuario"], config["clave"])
    datos = logica.autenticar(ejecutar, "limon1", "tec2026")
    assert datos["campus_id"] == 5
    try:
        logica.autenticar(ejecutar, "limon1", "mala")
        raise AssertionError("entró con clave mala")
    except logica.ErrorSigTec as error:
        assert "incorrectos" in str(error), str(error)
    return f"limon1 -> puerto {datos['puerto']}"


@prueba("Volver a entrar con otro usuario reemplaza las capas (no las duplica)")
def _():
    """Paso: Volver a entrar con otro usuario reemplaza las capas (no las duplica)."""
    plugin.ingresar("cartago1", "tec2026")
    grupos = [g.name() for g in QgsProject.instance().layerTreeRoot().children()]
    assert grupos == ["SIG-TEC - Campus Tecnológico Central Cartago"], grupos
    assert len(QgsProject.instance().mapLayers()) == 8


@prueba("unload() quita el botón del plugin")
def _():
    """Paso: unload() quita el botón del plugin."""
    plugin.unload()
    assert iface.acciones == []


QgsProject.instance().clear()
app.exitQgis()
print(f"RESULTADO {resultados.count(True)} OK {resultados.count(False)} FALLO")
sys.exit(0 if all(resultados) else 1)
