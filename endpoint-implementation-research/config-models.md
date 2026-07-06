# config-models

## Summary
Mapped how dstack configuration types are defined and registered end-to-end. All top-level config types live in src/dstack/_internal/core/models/configurations.py, discriminated by a `type: Literal[...]` field, and are aggregated into four unions there (AnyRunConfiguration, AnyApplyConfiguration, BaseApplyConfiguration.__root__, AnyDstackConfiguration) plus an ApplyConfigurationType enum. CLI-side dispatch happens via apply_configurators_mapping in src/dstack/_internal/cli/services/configurators/__init__.py where each configurator class declares TYPE = ApplyConfigurationType.<X>. There is NO generic server-side apply endpoint — each resource type (runs/fleets/gateways/volumes) has its own typed REST router registered in server/app.py and its own APIClient group in dstack/api/server/. No "endpoint" configuration type exists anywhere yet. ProfileParams (including `tags`) is mixed into run configurations only; fleets/gateways/volumes duplicate a subset of fields instead.

## Key files
- src/dstack/_internal/core/models/configurations.py — RunConfigurationType, BaseRunConfiguration, DevEnvironmentConfiguration, TaskConfiguration, ServiceConfiguration, ServiceConfigurationParams, ReplicaGroup, ProbeConfig, ScalingSpec, RateLimit, AnyRunConfiguration, RunConfiguration, parse_run_configuration, ApplyConfigurationType, AnyApplyConfiguration, BaseApplyConfiguration, parse_apply_configuration, AnyDstackConfiguration, DstackConfiguration — THE registration hub: 4 unions + 1 enum must be touched for a new top-level type (lines 1366-1463).
- src/dstack/_internal/cli/services/configurators/__init__.py — apply_configurators_mapping, run_configurators_mapping, get_apply_configurator_class, load_apply_configuration — CLI dispatch table (lines 27-49) and YAML parse entrypoint (yaml.safe_load -> parse_apply_configuration, lines 62-86).
- src/dstack/_internal/cli/services/configurators/base.py — BaseApplyConfigurator (TYPE: ClassVar[ApplyConfigurationType], apply_configuration, delete_configuration, register_args), ApplyEnvVarsConfiguratorMixin — Abstract base every new configurator subclasses; env-var CLI args + EnvSentinel resolution from os.environ.
- src/dstack/_internal/core/models/profiles.py — ProfileParams (lines 310-493), ProfileParamsConfig, Profile, ProfileRetry, UtilizationPolicy, Schedule, SpotPolicy, CreationPolicy, parse_duration, parse_off_duration, parse_idle_duration — Complete ProfileParams field list incl. tags; mixed into run configs via multiple inheritance.
- src/dstack/_internal/core/models/envs.py — Env, EnvSentinel, EnvVarTuple — Env is a plain pydantic BaseModel with __root__ Union[List[str], Dict[str, Union[str, EnvSentinel]]] — deliberately NOT a CoreModel.
- src/dstack/_internal/core/models/common.py — CoreModel, CoreConfig, generate_dual_core_model, Duration, EntityReference, ApplyAction — pydantic-duality dual models: strict __request__ (extra=forbid) vs __response__ (extra=ignore). Custom Config must go through generate_dual_core_model.
- src/dstack/_internal/core/models/fleets.py — FleetConfiguration, CommonFleetConfigurationProps (type: Literal["fleet"]), BackendFleetConfiguraionProps, SSHFleetConfigurationProps, FleetSpec, Fleet, FleetPlan, ApplyFleetPlanInput, FleetStatus — Non-run config pattern: no ProfileParams inheritance; FleetSpec = configuration + profile + merged_profile.
- src/dstack/_internal/core/models/gateways.py — GatewayConfiguration (type: Literal["gateway"]), GatewaySpec, Gateway, GatewayPlan, ApplyGatewayPlanInput, GatewayStatus — Simplest non-run config: flat CoreModel, no env, no ProfileParams; SUBMITTED/PROVISIONING/RUNNING/FAILED status enum is the closest analog to the planned endpoint lifecycle.
- src/dstack/_internal/core/models/volumes.py — BaseVolumeConfiguration (type: Literal["volume"]), AnyVolumeConfiguration, VolumeConfiguration, parse_volume_configuration, VolumeSpec, Volume, VolumeStatus — Two-stage discriminated parse: `type` then `backend`; explains why BaseApplyConfiguration vs AnyApplyConfiguration differ.
- src/dstack/_internal/cli/services/configurators/gateway.py — GatewayConfigurator (TYPE = ApplyConfigurationType.GATEWAY) — Best template for an async-provisioned resource configurator: get_plan -> confirm -> apply_plan -> poll status until RUNNING/FAILED.
- src/dstack/_internal/cli/services/configurators/run.py — BaseRunConfigurator, TaskConfigurator(:665), DevEnvironmentConfigurator(:680), ServiceConfigurator(:717), interpolate_env(:390) — Run-config CLI flow; ${{ env.* }} interpolation happens CLI-side.
- src/dstack/_internal/cli/commands/apply.py — ApplyCommand — Generic; dispatches on configuration.type via get_apply_configurator_class (line 92). No per-type edits needed.
- src/dstack/_internal/cli/commands/delete.py — DeleteCommand — Same generic dispatch (line 38); requires delete_configuration on the configurator.
- src/dstack/_internal/core/models/services.py — AnyModel, ChatModel, OpenAIChatModel, TGIChatModel, BaseChatModel — The `model` field type of ServiceConfiguration; discriminated on `format`.
- src/dstack/_internal/core/models/runs.py — RunSpec (:522), configuration field (:575), _merged_profile (:590-607) — How AnyRunConfiguration + Profile are merged into merged_profile — the pattern an endpoint spec with ProfileParams should replicate.
- src/dstack/_internal/server/app.py — register_routes (:239-269) — Server-side router registration; a new resource type needs its own router here.
- src/dstack/api/server/__init__.py — APIClient properties: fleets, runs, gateways, volumes, ... (:76-146) — Low-level HTTP client groups (dstack/api/server/_*.py); a new resource needs a new group.
- scripts/docs/gen_schema_reference.py — generate_schema_reference, sub_schema_reference — mkdocs hook expanding '#SCHEMA# dotted.model.Path' directives in mkdocs/docs/reference/dstack.yml/*.md.
- .github/workflows/build-artifacts.yml — line 248: DstackConfiguration.schema_json() — CI generates configuration.json editor schema from DstackConfiguration — picks up a new type automatically once added to AnyDstackConfiguration.

## Details
# Configuration types in dstack — ground truth (verified 2026-07-03, master @ 28ea5f86f)

No `endpoint` configuration type, `EndpointConfiguration` class, or `ENDPOINT` enum member exists anywhere in the codebase. `grep` confirms.

## 1. Run configurations — `src/dstack/_internal/core/models/configurations.py` (1463 lines)

### Discriminator & enums
- `RunConfigurationType(str, Enum)` (:77-80): `DEV_ENVIRONMENT = "dev-environment"`, `TASK = "task"`, `SERVICE = "service"`.
- Every configuration class carries `type: Literal["<value>"] = "<value>"` used as the pydantic discriminator.

### Base class
`class BaseRunConfiguration(CoreModel)` (:484) — `type: Literal["none"]` (overridden by subclasses). Fields:
- `name: Optional[str] = None`, `image: Optional[str] = None`, `user: Optional[str] = None`, `privileged: bool = False`, `entrypoint: Optional[str] = None`, `working_dir: Optional[str] = None`, `home_dir: str = "/root"` (deprecated), `registry_auth: Optional[RegistryAuth] = None`, `python: Optional[PythonVersion] = None`, `nvcc: Optional[bool] = None`, `single_branch: Optional[bool] = None`, `env: Env = Env()` (:540-543), `shell: Optional[str] = None`, `resources: ResourcesSpec = ResourcesSpec()` (:554-556), `priority: Optional[int]` (0..100), `volumes: List[MountPoint] = []`, `docker: Optional[bool] = None`, `repos: list[RepoSpec] = []`, `files: list[FilePathMapping] = []`, `setup: CommandsList = []` (deprecated).
- Validators coerce strings: `volumes` via `parse_mount_point`, `files` via `FilePathMapping.parse`, `repos` via `RepoSpec.parse`; mutual exclusions for image/python/docker/nvcc.

### Mixin param classes
- `ConfigurationWithPortsParams` (:657): `ports: List[Union[ValidPort, constr(regex=...), PortMapping]] = []` (`ValidPort = conint(gt=0, le=65536)` :53).
- `ConfigurationWithCommandsParams` (:672): `commands: CommandsList = []` + root_validator requiring `commands` or `image` (skipped when `replicas` is a list).
- `DevEnvironmentConfigurationParams` (:687): `ide` (vscode/cursor/windsurf/zed), `version`, `init: CommandsList`, `inactivity_duration`.
- `TaskConfigurationParams` (:768): `nodes: int = 1 (ge=1)`.

### Concrete classes (note MRO — ProfileParams first)
- `DevEnvironmentConfiguration(ProfileParams, BaseRunConfiguration, ConfigurationWithPortsParams, DevEnvironmentConfigurationParams, generate_dual_core_model(DevEnvironmentConfigurationConfig))` (:752) — `type: Literal["dev-environment"] = "dev-environment"` (:759).
- `TaskConfiguration(ProfileParams, BaseRunConfiguration, ConfigurationWithCommandsParams, ConfigurationWithPortsParams, TaskConfigurationParams, generate_dual_core_model(TaskConfigurationConfig))` (:782) — `type: Literal["task"] = "task"` (:790).
- `ServiceConfiguration(ProfileParams, BaseRunConfiguration, ConfigurationWithCommandsParams, ServiceConfigurationParams, generate_dual_core_model(ServiceConfigurationConfig))` (:1328) — `type: Literal["service"] = "service"` (:1335); property `replica_groups -> List[ReplicaGroup]` (:1337-1363).

Each has a paired `*Config` class (e.g. `ServiceConfigurationConfig` :1316) that composes `schema_extra` from `ProfileParamsConfig`, `BaseRunConfigurationConfig`, `ServiceConfigurationParamsConfig` — needed because pydantic-duality requires Config passed via `generate_dual_core_model()`.

### ServiceConfiguration own fields (`ServiceConfigurationParams` :961-1313)
- `port: Union[ValidPort, constr(regex=r"^[0-9]+:[0-9]+$"), PortMapping]` — REQUIRED; validator coerces int → `PortMapping(local_port=80, container_port=v)` (:1050-1056).
- `gateway: Optional[Union[bool, EntityReference, str]] = None` (str coerced to EntityReference).
- `strip_prefix: bool = True`.
- `model: Optional[AnyModel] = None` (:993-1003); validator `convert_model` (:1058-1062): str → `OpenAIChatModel(type="chat", name=v, format="openai")`. `AnyModel = Union[ChatModel]`; `ChatModel = Annotated[Union[TGIChatModel, OpenAIChatModel], Field(discriminator="format")]` (core/models/services.py:75-76). `OpenAIChatModel` has `prefix: str = "/v1"`.
- `https: Optional[Union[bool, Literal["auto"]]] = None`.
- `auth: bool = True`.
- `scaling: Optional[ScalingSpec] = None` (`ScalingSpec` :213 — metric Literal["rps"], target float, window, scale_up_delay/scale_down_delay Durations).
- `rate_limits: list[RateLimit] = []` (:282).
- `probes: Optional[list[ProbeConfig]] = None` (:1019-1026) — `None` = may get default when `model` set; `[]` = explicitly none. `ProbeConfig` (:365): `type: Literal["http"]`, `url` (default `/`), `method` (get/post/put/delete/patch/head), `headers: list[HTTPHeaderSpec]`, `body`, `timeout` (default 10s), `interval` (default 15s), `ready_after` (default 1), `until_ready` (default false). The default model probe is built server-side in `server/services/jobs/configurators/base.py::_openai_model_probe_spec` (:472-491): POST `{prefix}/chat/completions` with `{"model": name, "messages":[{"role":"user","content":"hi"}], "max_tokens":1}`, timeout `OPENAI_MODEL_PROBE_TIMEOUT = 30`.
- `replicas: Optional[Union[List[ReplicaGroup], Range[int]]] = None` (:1028-1040); `ReplicaGroup` (:817) has name, count: Range[int], scaling, resources, spot_policy, reservation, commands, image, python, nvcc, docker, privileged, router. Multiple root_validators enforce group vs top-level mutual exclusions (:1123-1313).
- `router: Optional[AnyServiceRouterConfig] = None` (from `core/models/routers.py`).
- `resources` (inherited): `ResourcesSpec` (core/models/resources.py:377) — cpu, memory, shm_size, gpu, disk.

### Unions & parsers (the registration hub)
- `AnyRunConfiguration = Union[DevEnvironmentConfiguration, TaskConfiguration, ServiceConfiguration]` (:1366).
- `class RunConfiguration(CoreModel)` (:1369): `__root__: Annotated[AnyRunConfiguration, Field(discriminator="type")]`.
- `def parse_run_configuration(data: dict) -> AnyRunConfiguration` (:1376-1381) — raises `ConfigurationError` on ValidationError.
- `class ApplyConfigurationType(str, Enum)` (:1384-1390): DEV_ENVIRONMENT, TASK, SERVICE, FLEET, GATEWAY, VOLUME.
- `AnyApplyConfiguration = Union[AnyRunConfiguration, FleetConfiguration, GatewayConfiguration, AnyVolumeConfiguration]` (:1393-1398).
- `class BaseApplyConfiguration(CoreModel)` (:1401-1421): `__root__: Annotated[Union[AnyRunConfiguration, FleetConfiguration, GatewayConfiguration, BaseVolumeConfiguration], Field(discriminator="type")]` — note `BaseVolumeConfiguration` here (not the backend union) because volumes need a second parse on `backend`.
- `def parse_apply_configuration(data: dict) -> AnyApplyConfiguration` (:1424-1437): pass 1 with `BaseApplyConfiguration.__response__` (extra ignored) to find the type; if not a volume, pass 2 strict (`BaseApplyConfiguration.parse_obj`, extra forbidden) for validation, return pass-1 object; volumes delegate to `parse_volume_configuration` (volumes.py:191).
- `AnyDstackConfiguration = Union[AnyRunConfiguration, FleetConfiguration, GatewayConfiguration, VolumeConfiguration]` (:1440-1445) — uses the `VolumeConfiguration` ROOT model, not `AnyVolumeConfiguration`.
- `class DstackConfiguration(CoreModel)` (:1448-1463): root over `AnyDstackConfiguration` with draft-07 `$schema` + `additionalProperties: True` — used ONLY by CI (`.github/workflows/build-artifacts.yml:248`: `python -c "from dstack._internal.core.models.configurations import DstackConfiguration; print(DstackConfiguration.schema_json())" > /tmp/json-schemas/configuration.json`).

## 2. Non-run configuration models

### Fleets — `core/models/fleets.py`
- `CommonFleetConfigurationProps` (:211): `type: Literal["fleet"] = "fleet"`, `name`, `placement`, `blocks`.
- `BackendFleetConfiguraionProps` (:232 — NOTE the typo "Configuraion" is the real class name): nodes (`FleetNodesSpec`), reservation, resources, backends, regions, availability_zones, instance_types, spot_policy, retry, max_price, idle_duration, `tags: Optional[Dict[str,str]]` (:298), backend_options. These duplicate ProfileParams-ish fields — fleets do NOT inherit ProfileParams.
- `SSHFleetConfigurationProps` (:345): ssh_config, `env: Env = Env()`.
- `FleetConfiguration(SSHFleetConfigurationProps, BackendFleetConfiguraionProps, CommonFleetConfigurationProps, generate_dual_core_model(FleetConfigurationConfig))` (:362).
- `FleetSpec` (:393): `configuration: FleetConfiguration`, `configuration_path: Optional[str]`, `profile: Profile`, `merged_profile: Annotated[Profile, Field(exclude=True)]` computed by root_validator `_merged_profile` (:408-424) — loops `for key in ProfileParams.__fields__` and overrides profile values with non-None config values.
- Runtime model `Fleet` (:427): id, name, project_name, spec, created_at, `status: FleetStatus` (SUBMITTED/ACTIVE/TERMINATING/TERMINATED/FAILED :34-41 — comment says SUBMITTED/FAILED reserved for async processing), status_message, instances. Plan models: `FleetPlan` (:438), `ApplyFleetPlanInput` (:456).

### Gateways — `core/models/gateways.py`
- `GatewayConfiguration(CoreModel)` (:59): `type: Literal["gateway"] = "gateway"`, name, default, `backend: BackendType` (required), `region: str` (required), instance_type, router, domain, public_ip, certificate, replicas, `tags` (:111). Flat class — no ProfileParams, no env, no resources.
- `GatewaySpec` (:125): configuration + configuration_path only.
- `GatewayStatus` (:17): SUBMITTED/PROVISIONING/RUNNING/FAILED — closest analog for an async-provisioned endpoint lifecycle. Runtime `Gateway` (:141) has status, status_message, created_at.
- `GatewayPlan` (:176), `ApplyGatewayPlanInput` (:185).

### Volumes — `core/models/volumes.py`
- `BaseVolumeConfiguration(CoreModel)` (:36): `type: Literal["volume"] = "volume"`, `backend: Any` (overridden per subclass with `Literal[BackendType.X]`), name, size, auto_cleanup_duration, `tags` (:59).
- Backend subclasses: `AWSVolumeConfiguration` (:113), `GCPVolumeConfiguration` (:121), `RunpodVolumeConfiguration` (:129), `KubernetesVolumeConfiguration` (:137); `AnyVolumeConfiguration` union (:179); `VolumeConfiguration` root model discriminated on `backend` (:187); `parse_volume_configuration` (:191).
- `VolumeStatus` (:19): SUBMITTED/PROVISIONING/ACTIVE/FAILED with `finished_statuses()`.
- `VolumeSpec` (:198): configuration + configuration_path.

### Key difference from run configs
Non-run configs have `name` for the resource itself, plain status enums, `<X>Spec` wrapper `{configuration, configuration_path[, profile]}`, `<X>Plan`, and `Apply<X>PlanInput{spec, current_resource}` models. Server exposes per-type REST endpoints; CLI configurators call `self.api.client.<resource>.get_plan/apply_plan/delete` and poll.

## 3. ProfileParams — `core/models/profiles.py:310-493` (complete)
`backends: Optional[List[BackendType]]`, `regions: Optional[List[str]]`, `availability_zones: Optional[List[str]]`, `instance_types: Optional[List[str]]`, `reservation: Optional[str]`, `spot_policy: Optional[SpotPolicy]` (spot/on-demand/auto), `retry: Optional[Union[ProfileRetry, bool]]`, `max_duration: Optional[Union[Literal["off"], int]]`, `stop_duration: Optional[Union[Literal["off"], int]]`, `max_price: Optional[float] (gt=0)`, `creation_policy: Optional[CreationPolicy]` (reuse/reuse-or-create), `idle_duration: Optional[int]`, `utilization_policy: Optional[UtilizationPolicy]`, `startup_order: Optional[StartupOrder]`, `stop_criteria: Optional[StopCriteria]`, `schedule: Optional[Schedule]` (cron), `fleets: Optional[list[Union[EntityReference, str]]]`, `instances: Optional[List[InstanceSelector]] (min_items=1)`, `tags: Optional[Dict[str, str]]` (:462-471, validated by `tags_validator`), `backend_options: Optional[List[AnyBackendProfileOptions]]`. All Optional/None-default. Duration validators pre-parse "2h"/"off" strings. `Profile = ProfileProps(name, default) + ProfileParams` (:514). `ProfileParamsConfig.schema_extra` (:289) adds string/bool alt types for max_duration/stop_duration/idle_duration/instances.

## 4. Env — `core/models/envs.py`
`class Env(BaseModel)` (:42) — custom root model: `__root__: Union[List[str matching ^([a-zA-Z_][a-zA-Z0-9_]*)(=.*$|$)], Dict[str, Union[str, EnvSentinel]]] = {}`. Docstring explicitly: NOT a CoreModel because pydantic-duality doesn't play well with custom root models. List form normalized to dict by validator; bare `VAR` becomes `EnvSentinel(key=VAR)`. API: `as_dict()` (raises ValueError if sentinels unresolved), `update()`, `keys/values/items`, `__getitem__/__setitem__`, dict-like `copy()`. Sentinel resolution from `os.environ` happens CLI-side in `ApplyEnvVarsConfiguratorMixin.apply_env_vars` (cli/services/configurators/base.py:95-103); `-e KEY[=VALUE]` args registered by `register_env_args` (:83-93).

## 5. Tags
Yes, supported: `ProfileParams.tags` gives all run configurations tags for free; fleets (fleets.py:298), gateways (gateways.py:111), volumes (volumes.py:59) declare their own. Validation: `src/dstack/_internal/utils/tags.py::tags_validator` — key `^[_\-a-zA-Z0-9]{1,60}$`, value `^[a-zA-Z0-9 .:/=_\-+@]{0,256}$`. No other "metadata" field exists on configurations.

## 6. YAML parsing/validation flow for `dstack apply`
1. `ApplyCommand._command` (cli/commands/apply.py:72) → `load_apply_configuration(args.configuration_file)` (cli/services/configurators/__init__.py:62-86): resolves `$PWD/.dstack.yml`/`.yaml` or `-f FILE` or stdin (`-`), `yaml.safe_load`, then `parse_apply_configuration(dict)`.
2. `get_apply_configurator_class(configuration.type)` (:52-55) — `ApplyConfigurationType(configurator_type)` then dict lookup in `apply_configurators_mapping` (:27-39, built from class list `[DevEnvironmentConfigurator, TaskConfigurator, ServiceConfigurator, FleetConfigurator, GatewayConfigurator, VolumeConfigurator]` keyed by `cls.TYPE`).
3. Configurator instantiated with `api_client=self.api` (`dstack.api._public.Client`), `configurator.get_parser()` parses per-type extra args, then `apply_configuration(conf, configuration_path, command_args, configurator_args)`.
4. `dstack delete/destroy` (cli/commands/delete.py:35-44) uses the same dispatch and calls `delete_configuration`.
5. `dstack apply -h TYPE` (apply.py:27-36) parses TYPE via the `ApplyConfigurationType` enum.
6. Run-config interpolation: `BaseRunConfigurator.interpolate_env` (run.py:390-408) uses `VariablesInterpolator({"env": ...}, skip=["secrets"])` on registry_auth and probe fields.

Server side: there is NO generic apply/config endpoint. Runs: client sends `RunSpec` (core/models/runs.py:522; `configuration: Annotated[AnyRunConfiguration, Field(discriminator="type")]` :575; `merged_profile` root_validator :590-607) to `runs` router. Fleets/gateways/volumes have their own typed routers. Routers registered in `server/app.py::register_routes` (:239-269): server, users, auth, projects, backends, fleets, instances, repos, runs, gpus, metrics, logs, secrets, gateways, volumes, service_proxy, model_proxy, prometheus, files, events, templates, exports, imports, sshproxy, public_keys. Low-level client groups: `dstack/api/server/_*.py` with properties on `APIClient` (api/server/__init__.py:76-146). Run-type-only server dispatch: `server/services/jobs/__init__.py::_get_job_configurator` (:316-333) maps `RunConfigurationType` → `{DevEnvironmentJobConfigurator, TaskJobConfigurator, ServiceJobConfigurator}` (server/services/jobs/configurators/{dev,task,service}.py each with `TYPE: RunConfigurationType`).

## 7. EXHAUSTIVE checklist to add a new top-level config type `endpoint`

Core models:
1. `src/dstack/_internal/core/models/configurations.py` — define `EndpointConfiguration` (with `type: Literal["endpoint"] = "endpoint"`); add `ENDPOINT = "endpoint"` to `ApplyConfigurationType` (:1384); add the class to `AnyApplyConfiguration` (:1393), to `BaseApplyConfiguration.__root__` union (:1411), and to `AnyDstackConfiguration` (:1440). (Or define the model in a new `core/models/endpoints.py` and import it, like fleets/gateways/volumes do — beware circular imports: configurations.py already imports fleets/gateways/volumes/profiles.)
2. If it's a standalone resource (like gateway/volume): also define `EndpointSpec {configuration, configuration_path}`, `Endpoint` (runtime: id, name, project_name, created_at, status, status_message, ...), `EndpointStatus` enum (mirror `GatewayStatus`: SUBMITTED/PROVISIONING/RUNNING(ACTIVE)/FAILED), `EndpointPlan`, `ApplyEndpointPlanInput`.

CLI:
3. New `src/dstack/_internal/cli/services/configurators/endpoint.py`: `class EndpointConfigurator(ApplyEnvVarsConfiguratorMixin, BaseApplyConfigurator[EndpointConfiguration])` with `TYPE = ApplyConfigurationType.ENDPOINT`, implementing `apply_configuration()` and `delete_configuration()` (both abstract), optionally `register_args()`/`apply_args()`. GatewayConfigurator (gateway.py:37) is the closest template (async provisioning + status polling).
4. `src/dstack/_internal/cli/services/configurators/__init__.py` — add `EndpointConfigurator` to the class list building `apply_configurators_mapping` (:30-39). Do NOT add to `run_configurators_mapping` (run types only). `dstack apply`/`dstack delete`/`dstack apply -h endpoint` then work with no further CLI edits.

Server (endpoint-as-own-resource path):
5. New router `src/dstack/_internal/server/routers/endpoints.py` + registration in `server/app.py::register_routes` (:239).
6. New `src/dstack/api/server/_endpoints.py` APIClient group + property in `src/dstack/api/server/__init__.py` (pattern :96-131), so the CLI configurator can call `self.api.client.endpoints.*`.
7. (Server services/DB/background processing are separate topics — not covered here.)

Docs/schema:
8. `mkdocs/docs/reference/dstack.yml/endpoint.md` with `#SCHEMA# dstack._internal.core.models....EndpointConfiguration` directives (processed by `scripts/docs/gen_schema_reference.py`).
9. `mkdocs.yml` nav (:343-349) — add `- endpoint: docs/reference/dstack.yml/endpoint.md`.
10. `mkdocs/docs/reference/dstack.yml.md` index — add link to the new page.
11. Editor JSON schema (`.github/workflows/build-artifacts.yml:248`) regenerates automatically from `DstackConfiguration` once step 1 includes the type in `AnyDstackConfiguration`.

Optional:
12. `src/dstack/api/__init__.py` — public alias (pattern: `Service = _ServiceConfiguration` :28-30).
13. If ProfileParams is inherited, also create `EndpointConfigurationConfig(ProfileParamsConfig)` composing `schema_extra` (pattern: `ServiceConfigurationConfig` :1316-1325) and pass it via `generate_dual_core_model(...)` as the last base class.

## Gotchas
1) Pydantic v1 syntax throughout (`root_validator`/`validator`, `__root__` models, `constr(regex=...)`) — do not write v2-style code. 2) pydantic-duality: every CoreModel is dual (`__request__` extra=forbid / `__response__` extra=ignore). NEVER define `class Config` directly on a model — it breaks `__response__`; pass a custom Config class via `generate_dual_core_model(MyConfig)` as a BASE CLASS (last in MRO), and when combining mixins, the Config class must manually chain each parent's `schema_extra` (see ServiceConfigurationConfig at configurations.py:1316). 3) `BaseRunConfiguration.type` is `Literal["none"]` with NO default — every concrete subclass overrides it with its own Literal + default; the discriminator for apply configs is `type`, and volumes have a SECOND discriminator `backend` requiring the two-stage `parse_apply_configuration` (first pass parses with `__response__` i.e. extras ignored, second strict pass validates). A new type with only `type` as discriminator goes in the "Final configurations" part of `BaseApplyConfiguration.__root__`. 4) `AnyDstackConfiguration` (editor JSON schema union) uses the wrapped `VolumeConfiguration` root model, not `AnyVolumeConfiguration` — subtle asymmetry with `AnyApplyConfiguration`. 5) MRO matters: run configs list `ProfileParams` FIRST (`ServiceConfiguration(ProfileParams, BaseRunConfiguration, ...)`); ProfileParams already contains `tags`, `schedule`, `fleets`, `idle_duration` etc., so an endpoint config inheriting ProfileParams gets all of those including tags — no need to re-declare. 6) Fleet/gateway/volume configs do NOT inherit ProfileParams (fleets duplicate ~12 of its fields in `BackendFleetConfiguraionProps` — note the real class name has the typo "Configuraion"); only run configs use the merged_profile pattern (`RunSpec._merged_profile` runs.py:590 iterates `ProfileParams.__fields__`). 7) `Env` is NOT a CoreModel (plain BaseModel with custom root) and `EnvSentinel` values (bare `VAR` entries) are resolved from os.environ CLI-side only (`ApplyEnvVarsConfiguratorMixin.apply_env_vars`); a server-side agent creating configs from an endpoint's env must handle/forbid unresolved sentinels itself (`Env.as_dict()` raises ValueError on unresolved). 8) `get_apply_configurator_class` does `ApplyConfigurationType(configurator_type)` — forgetting the enum member makes `dstack apply` crash with ValueError before any useful message. 9) `ServiceConfiguration.port` is REQUIRED (no default) and coerced to `PortMapping(local_port=80, ...)`; `model: str` is coerced to `OpenAIChatModel(type="chat", format="openai", prefix="/v1")` — a preset/agent-generated service config must set `port` and should set `model` for the OpenAI-compatible proxy + default `/v1/chat/completions` probe (probe default is applied server-side in `server/services/jobs/configurators/base.py::_openai_model_probe_spec`, not in the model). 10) Old-style server background tasks were reworked: `server/background/pipeline_tasks` + `server/background/scheduled_tasks` (see app.py:25-27 imports `start_pipeline_tasks`, `start_scheduled_tasks`) — do not reference a `background/tasks` module. 11) The CLI never sends `AnyApplyConfiguration` to the server; each type maps to its own typed REST API (RunSpec/FleetSpec/GatewaySpec/VolumeSpec + plan/apply-plan endpoints), so a new endpoint type needs its own router + API client group, not a hook into an existing generic endpoint. 12) `dstack delete` requires `delete_configuration` implemented (abstract), and gateway/volume configurators poll async deletion — deletion of the new resource should follow the same async pattern.
