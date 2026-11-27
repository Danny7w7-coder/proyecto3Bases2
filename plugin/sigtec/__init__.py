"""Plugin SIG-TEC para QGIS. QGIS llama a classFactory() al cargar el plugin."""


def classFactory(iface):
    """QGIS llama a esta función al cargar el plugin. Crea y devuelve la clase principal."""
    from .plugin import SigTecPlugin
    return SigTecPlugin(iface)
