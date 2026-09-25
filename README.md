# Booking Engine API

API de reservas para recursos de capacidad uno: una sala, una agenda o una estación de atención. Incluye horarios semanales, disponibilidad, cancelaciones y protección contra reservas solapadas mediante una restricción de PostgreSQL.

**Stack:** Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2, Psycopg 3, PostgreSQL 17+, Alembic, JWT, Argon2, `zoneinfo`, pytest, Ruff y Docker Compose.

## Arranque con Docker

Requisitos: Docker Engine con Compose v2. Desde esta carpeta:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
# Copia el valor generado a JWT_SECRET en .env.
docker compose up --build -d
```

- Swagger: [localhost:8002/docs](http://localhost:8002/docs)
- OpenAPI: [localhost:8002/openapi.json](http://localhost:8002/openapi.json)
- Estado de la base: [localhost:8002/ready](http://localhost:8002/ready)

Compose espera a PostgreSQL, aplica las migraciones y arranca la API. En bash usa `cp` para copiar `.env.example`. Los puertos se publican solo en localhost. Usa una clave JWT diferente a la del proyecto de gastos. Las credenciales de ejemplo son para desarrollo; cambia la contraseña de PostgreSQL para otros entornos. Codifica los caracteres reservados de las contraseñas al construir URLs de conexión.

## Desarrollo local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
Copy-Item .env.example .env
# Configura JWT_SECRET en .env.
docker compose up -d db
alembic upgrade head
uvicorn app.main:app --reload --port 8002
```

En Linux/macOS activa con `source .venv/bin/activate`. Si ya tienes PostgreSQL, configura `DATABASE_URL` y omite Docker. El usuario de migraciones debe poder instalar `btree_gist`, o un administrador debe instalar previamente la extensión.

## Probar el flujo

1. Registra una cuenta de proveedor y otra de cliente mediante `/api/v1/auth/register`.
2. Obtén un token por cuenta en `/api/v1/auth/token` usando formulario con `username=<email>`.
3. Como proveedor, crea un servicio con zona IANA y duración; añade una ventana semanal.
4. Como cliente, consulta la disponibilidad para una fecha futura y reserva uno de los timestamps devueltos.
5. Repite la reserva: recibirás `409`. Cancélala y el intervalo vuelve a estar disponible.

[examples.http](./examples.http) incluye el flujo completo. Actualiza su fecha a una fecha futura que corresponda al día de la ventana. `python -m app.demo` o `docker compose exec api python -m app.demo` crea un proveedor y un servicio de lunes a viernes, de 09:00 a 17:00, en `America/Bogota`, pidiendo credenciales de forma interactiva.

## Endpoints

| Método | Ruta bajo `/api/v1` | Función |
| --- | --- | --- |
| POST | `/auth/register`, `/auth/token` | Registro y login |
| GET | `/auth/me` | Cuenta autenticada |
| GET, POST | `/services` | Catálogo y creación de servicios |
| GET | `/services/{id}` | Detalle del servicio |
| GET, POST | `/services/{id}/windows` | Horarios semanales |
| DELETE | `/services/{id}/windows/{window_id}` | Retirar horario |
| GET | `/services/{id}/availability?day=YYYY-MM-DD` | Intervalos disponibles |
| GET, POST | `/bookings` | Mis reservas y nueva reserva |
| GET | `/bookings/{id}` | Detalle de reserva |
| POST | `/bookings/{id}/cancel` | Cancelación idempotente |

`GET /services?mine=true` muestra los servicios propios. `GET /bookings?as_provider=true` muestra reservas de los servicios administrados por la cuenta. Los listados de servicios y reservas admiten `limit`/`offset`; las reservas incluyen `total`.

## Reglas y concurrencia

```mermaid
erDiagram
    USER ||--o{ SERVICE : manages
    SERVICE ||--o{ SCHEDULE_WINDOW : defines
    SERVICE ||--o{ BOOKING : receives
    USER ||--o{ BOOKING : books
```

- Cada servicio representa **un recurso independiente con capacidad uno**. Servicios diferentes del mismo propietario pueden recibir reservas simultáneas; para representar una única agenda compartida usa un solo servicio. No hay capacidad múltiple ni agenda compartida entre servicios.
- Cualquier usuario registrado puede crear servicios; es propietario de los que crea. Solo el propietario modifica horarios. Cliente y propietario pueden consultar o cancelar una reserva; terceros reciben `404`.
- Lunes es `0`; domingo es `6`. Las ventanas usan horas locales sin offset, con precisión de minutos, y no cruzan medianoche. No pueden superponerse.
- Los slots se alinean al inicio de cada ventana. La duración es fija, de 5 a 480 minutos. Las reservas requieren timestamps con zona u offset explícito y deben coincidir con un slot futuro, dentro de los próximos 365 días.
- PostgreSQL guarda timestamps con zona horaria; la disponibilidad devuelve instantes en UTC. `zoneinfo` convierte según la zona del servicio. Se omiten horas inexistentes, ambiguas y slots que cambian de duración real durante una transición DST.
- Una restricción `EXCLUDE USING gist` sobre `(service_id, tstzrange(starts_at, ends_at, '[)'))`, aplicada a reservas confirmadas, impide cualquier solapamiento. Los intervalos son semiabiertos: una reserva puede comenzar al terminar otra. No depende de una comprobación previa vulnerable a carreras.
- Reservas concurrentes pueden compartir el bloqueo de lectura del servicio; editar horarios requiere un bloqueo exclusivo. Así se evita reservar sobre una ventana retirada durante la operación. La exclusión de PostgreSQL decide el conflicto entre reservas.
- Cancelar una reserva futura es idempotente y libera el intervalo. Las reservas iniciadas no pueden cancelarse. Retirar una ventana impide nuevas reservas pero conserva las confirmaciones existentes.

La aplicación separa contratos (`schemas.py`), reglas de calendario (`scheduling.py`), casos de uso (`api.py`), persistencia (`models.py`, `migrations/`) y configuración/autenticación (`core/`). Las migraciones contienen DDL congelado, sin importar modelos actuales.

## Pruebas y calidad

**Usa una base desechable cuyo nombre termine en `_test`: las pruebas vacían sus tablas.** La suite usa PostgreSQL real y las migraciones del proyecto.

```powershell
docker compose -f compose.test.yaml up -d --wait
$env:TEST_DATABASE_URL='postgresql+psycopg://test:test@localhost:55434/bookings_test'
$env:DATABASE_URL=$env:TEST_DATABASE_URL
$env:JWT_SECRET='test-only-secret-never-use-in-production-12345'
alembic upgrade head
alembic check
pytest --cov=app --cov-report=term-missing
ruff check .
ruff format --check .
docker compose -f compose.test.yaml down
```

En bash usa `export`. Se cubren dos solicitudes concurrentes (una `201`, otra `409`), solapamientos parciales mediante SQL directo, intervalos adyacentes, permisos, cancelación, horarios inválidos, offsets equivalentes y transiciones DST. GitHub Actions prueba Python 3.12/3.13 con PostgreSQL 17.

Las dependencias de ejecución están fijadas en `requirements.lock`; las de desarrollo en `requirements-dev.lock`. Los tokens JWT verifican algoritmo, audiencia, emisor y expiración; las contraseñas usan Argon2. Incluye `X-Request-ID`, logs de duración, `/health` y `/ready`.

## Funciones añadidas

- `GET /api/v1/services?search=python` busca nombres sin distinguir mayúsculas, tratando `%` y `_` literalmente. Se combina con `mine=true`.
- `GET /api/v1/bookings?status=confirmed` filtra por `confirmed` o `cancelled`. Se combina con `as_provider=true`, paginación y fechas.
- `starts_from` es inclusivo y `starts_before` es exclusivo; ambos requieren timestamps con zona u offset. Un intervalo invertido o vacío devuelve `422`.
- `POST /api/v1/bookings/{id}/reschedule` recibe `{"starts_at":"2026-11-02T10:00:00-05:00"}`. Cliente o propietario pueden mover una reserva futura y confirmada dentro del mismo servicio. Conserva su ID, libera el intervalo anterior y aplica la restricción de solapamientos. Si el destino está ocupado devuelve `409` y mantiene la reserva original. Repetir el horario actual es válido.
- `GET /api/v1/services/{id}/availability-range?day_from=2026-11-02&day_to=2026-11-08` devuelve disponibilidad por día, incluidos los días vacíos. Admite hasta 31 días inclusivos, dentro del horizonte de 365 días del servicio. Hace una sola consulta de reservas para todo el intervalo y utiliza un recorrido ordenado para retirar los intervalos ocupados.
- Las respuestas bajo `/api/v1/`, incluidos los errores, llevan `Cache-Control: no-store`, junto con cabeceras `nosniff` y `no-referrer`.

Los endpoints adicionales están en `app/features/`. CI construye la imagen Docker y comprueba su importación y OpenAPI como usuario sin privilegios y sin acceso a red. La suite también verifica los datos de demostración y que una reprogramación rechazada conserve la reserva anterior.

## Alcance

No incluye pagos, notificaciones, festivos, excepciones por fecha, lista de espera, refresh tokens o recuperación de contraseñas. Los servicios no se editan ni eliminan en esta versión para mantener estables las reglas de las reservas existentes. La disponibilidad es una fotografía: un slot puede ocuparse antes del POST y devolver `409`. Para publicar la API añade TLS, límites de solicitudes, gestión de secretos y respaldos según el entorno.

## Repositorio e historial

Repositorio: [ElierPi/booking-system-api](https://github.com/ElierPi/booking-system-api).

El historial se preparó el 31 de octubre de 2026 para organizar el portafolio. Las fechas de autor y de commit se distribuyeron entre enero y septiembre de 2026; no representan las fechas originales de desarrollo. Véase [HISTORY.md](./HISTORY.md).

Referencias: [restricciones de exclusión en PostgreSQL](https://www.postgresql.org/docs/17/rangetypes.html#RANGETYPES-CONSTRAINT), [autenticación JWT en FastAPI](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
