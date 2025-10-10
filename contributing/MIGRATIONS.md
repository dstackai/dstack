# Database migrations

`dstack` uses Alembic to manage database migrations. If you modify any SQLAlchemy
[models](../src/dstack/_internal/server/models.py) or related data structures,
generate a new migration with Alembic:

```shell
cd src/dstack/_internal/server/
alembic revision -m "<some message>" --autogenerate
```

Then adjust the generated migration if needed.

## Deployment-compatible migrations

The `dstack` server claims to support multi-replica setups with zero-downtime deployments.
This means DB migrations should not make changes that break old replicas.
Incompatible changes should be introduced in multiple stages (releases), following
the [expand and contract pattern](https://www.prisma.io/dataguide/types/relational/expand-and-contract-pattern).

**Note**: If it's impossible to make the migration compatible with older versions, the PR should say so explicitly, so that the change is planned and released with the migration notice.

Below are some common changes and how to make them.

### Removing a column

1. First release:
   * Stop reading the column. In SQLAlchemy this can be done by setting `deferred=True` on a model field.
2. Second release:
   * Drop the column.

### Changing a column

These steps apply to **renaming a column** or **changing the type of a column**

1. First release:
   * Introduce a new column with the new type.
   * Write to both the new and the old column.
2. Second release:
   * Migrate data from the old column to the new column.
   * Start reading the new column.
   * Stop reading the old column.
   * Stop writing to the old column.
3. Third release:
   * Drop the old column.

### Altering multiple tables

Altering a table requires Postgres to [take an ACCESS EXCLUSIVE lock](https://www.postgresql.org/docs/current/sql-altertable.html). (This applies not only to statements that rewrite the tables but also to statements that modify tables metadata.) Altering multiple tables can cause deadlocks due to conflict with read operations since the `dstack` server does not define an order for read operations. Altering multiple tables should be done in separate transactions/migrations.
