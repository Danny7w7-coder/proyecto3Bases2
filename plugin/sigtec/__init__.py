"""Plugin SIG-TEC para QGIS. QGIS llama a classFactory() al cargar el plugin."""


def classFactory(iface):
    from .plugin import SigTecPlugin
    return SigTecPlugin(iface)
