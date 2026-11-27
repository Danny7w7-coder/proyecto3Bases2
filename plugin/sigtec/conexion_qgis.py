"""
Ejecutor de SQL con la conexión propia de QGIS.
Se usa solo si psycopg2 no está disponible en el Python de QGIS.
"""
from qgis.core import QgsDataSourceUri, QgsProviderConnectionException, QgsProviderRegistry

from .logica import ErrorSigTec, armar_sql, limpiar_error


def ejecutor_qgis(host, puerto, base, usuario, clave):
    """Devuelve una función ejecutar(sql, parametros) igual a la de psycopg2."""
    uri = QgsDataSourceUri()
    uri.setConnection(host, str(puerto), base, usuario, clave)
    metadatos = QgsProviderRegistry.instance().providerMetadata("postgres")

    def ejecutar(sql, parametros=()):
        """Ejecuta una consulta con la conexión de QGIS y devuelve las filas como diccionarios."""
        try:
            conexion = metadatos.createConnection(uri.uri(False), {})
            resultado = conexion.execSql(armar_sql(sql, parametros))
            columnas = resultado.columns()
            return [dict(zip(columnas, fila)) for fila in resultado.rows()]
        except QgsProviderConnectionException as error:
            raise ErrorSigTec(limpiar_error(str(error)))

    return ejecutar
