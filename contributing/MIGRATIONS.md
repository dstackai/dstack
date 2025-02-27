# Database migrations

`dstack` uses Alembic to manage database migrations. If you modify any SQLAlchemy
[models](../src/dstack/_internal/server/models.py) or related data structures,
generate a new migration with Alembic:

```shell
cd src/dstack/_internal/server/
alembic revision -m "<some message>" --autogenerate
```

Then adjust the generated migration if needed.

## PostgreSQL enums

If you modify any enums used in SQLAlchemy models, you will need to set up PostgreSQL
in order to generate a PostgreSQL-specific enum migration.

1. Run PostgreSQL.

   ```shell
   docker run --rm -p 5432:5432 -e POSTGRES_PASSWORD=password postgres
   ```

1. Create a database for `dstack`.

   ```shell
   psql -h localhost -U postgres --command "CREATE DATABASE dstack"
   ```

1. Run `dstack server` once to create the previous database schema.

   ```shell
   DSTACK_DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/dstack dstack server
   ```

1. Generate the migration.

   ```shell
   cd src/dstack/_internal/server/
   DSTACK_DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/dstack alembic revision -m "<some message>" --autogenerate
   ```
