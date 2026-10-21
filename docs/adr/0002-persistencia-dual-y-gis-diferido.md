# ADR 0002 — Persistencia dual (PostgreSQL + SQLite) y PostGIS diferido

**Fecha:** 2026-10-20 · **Estado:** aceptado

## Contexto

La especificación elige PostgreSQL + PostGIS. En la máquina de desarrollo no hay
cliente ni servidor de Postgres instalado; sí hay Docker. Los tests deben poder
correr sin levantar contenedores, y la aplicación debe poder arrancar sin
infraestructura para que la vertical sea verificable de inmediato.

## Decisión

Una sola definición de modelos y una sola cadena de migraciones para dos
motores:

- **PostgreSQL 16** es el modo de referencia (`docker compose`), el que se usa
  para integración y el que se asume en producción local.
- **SQLite** es el modo de arranque cero: tests y `make run-local`.

La elección es una variable de entorno (`DATABASE_URL`). Los tipos se
mantuvieron portables: `JSONType` (`JSON` con variante `JSONB`),
`Numeric(16,2)` para dinero, `Float` para `lat`/`lon`.

PostGIS **no** se usa todavía. Las consultas espaciales que la Etapa 1 necesita
son «distancia entre dos puntos» y «ciudades dentro de un territorio», y ambas
se resuelven con haversine en Python sobre un conjunto de datos de ocho ciudades.

## Razones

- Un test de dominio que exige un contenedor es un test que se deja de correr.
- Introducir PostGIS antes de tener una consulta que lo necesite es pagar
  complejidad por adelantado y degradar la portabilidad de las migraciones.
- La degradación queda documentada, que es lo que la especificación pide para
  instalaciones sin GIS avanzado.

## Consecuencias

- Hay que evitar SQL específico de un dialecto en los servicios. Lo vigila
  `backend/tests/test_persistence_portability.py`, que corre el mismo caso de uso
  contra SQLite.
- Cuando llegue la primera consulta espacial real (contención en polígono,
  vecindad), se añade la columna `geom` y un índice GiST en una migración
  condicionada al dialecto, con la ruta Python como respaldo.
- `Numeric` en SQLite vuelve como `Decimal` solo si se le pide; el código del
  dominio usa `Decimal` explícito y nunca `float` para dinero.
