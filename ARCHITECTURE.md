
# dstack architecture

## Project structure

* `runner/` – source code for the `dstack` runner
* `src/` – source code for the `dstack` Python package that includes the CLI and the server
    * `dstack/`
        * `_internal/` – modules hidden from the users of the `dstack` Python API
            * `cli/` – CLI source code
            * `core/` – core `dstack` business logic that is not API, CLI or server specific. Although most of it is used only on the server side as of now (e.g. backends).
                * `backends/` – core backends logic (e.g. compute provisioning, pricing, etc)
                * `models/` – core `dstack` pydantic models. For simplicity, server-specific models also live here. Put the model here if unsure.
                    * `backends/` – backend-specific models such as configs used by the server
                * `services/` – other business logic implemented on top of `models/`
            * `server/` – server source code
                * `background/` – server background workers
                * `migrations/` – alembic migrations
                * `routers/` – API endpoints implementation, a thin wrapper around `services/`.
                * `schemas/` – request/response-specific pydantic models. Other server models live in `dstack._internal.core.models`.
                * `security/` – permissions 
                * `services/` – core server business logic
                    * `backends/`
                        * `configurators/` – backend configurators responsible for configuring and creating backends from API configs
                    * `jobs/`
                        * `configurators/` – job configurators responsible for making `JobSpec` from `RunSpec`
                * `utils/` – server-specific utils
                * `alembic.ini`
                * `db.py` – db class and utils
                * `main.py` – server entrypoint
                * `models.py` – sqlalchemy models
                * `settings.py` – server global settings
            * `utils/` – utils common for all modules
        * `api/` – Python client for the `dstack` server API
        * `core/` – core Python API modules (e.g. `dstack` errors)
    * `tests/`