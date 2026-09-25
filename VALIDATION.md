# Validación de las mejoras

Preparadas y verificadas el 31 de octubre de 2026, usando Python 3.12.14 y PostgreSQL 18.6 real, con una base de pruebas desechable.

- 23 pruebas aprobadas; cobertura de sentencias de `app/`: 96%.
- `alembic check`: sin diferencias entre modelos y esquema migrado.
- Ruff: lint y formato correctos.
- Incluye dos reservas simultáneas y dos reprogramaciones simultáneas. En la reprogramación una solicitud recibe `200` y la otra `409`; la reserva que pierde el conflicto conserva su horario original.
- Pruebas adicionales: filtros combinados, offsets de timestamps, rangos de disponibilidad, permisos, cancelación, DST, cabeceras y datos de demostración.
- El workflow prueba Python 3.12/3.13 con PostgreSQL 17. En Python 3.12 construye la imagen Docker y valida importación y OpenAPI sin privilegios y sin red.

Docker no está instalado en el entorno local; esa comprobación se delega a GitHub Actions. La suite local emite un aviso de deprecación del adaptador HTTPX de Starlette; las pruebas pasan. Las fechas asignadas a los commits se explican en `HISTORY.md`.
