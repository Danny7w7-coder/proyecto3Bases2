# Imagen de cada nodo SIG-TEC: PostgreSQL + PostGIS oficial.
# Solo agregamos la carpeta donde se archivan los WAL (para PITR).
ARG POSTGIS_IMAGE=postgis/postgis:17-3.5
FROM ${POSTGIS_IMAGE}

# La carpeta debe pertenecer al usuario postgres para que archive_command pueda copiar ahí.
# Cuando Docker monta un volumen vacío en esta ruta, copia este dueño al volumen.
RUN mkdir -p /wal_archive && chown postgres:postgres /wal_archive
