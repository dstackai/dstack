import pytest

from dstack._internal.core.models.routers import ReplicaGroupRouterConfig, RouterType


class TestReplicaGroupRouterConfig:
    def test_accepts_legacy_smg_value(self):
        router = ReplicaGroupRouterConfig.model_validate({"type": "sglang"})
        assert router.type == RouterType.SMG

    def test_accepts_legacy_smg_value_from_json(self):
        router = ReplicaGroupRouterConfig.model_validate_json('{"type": "sglang"}')
        assert router.type == RouterType.SMG

    @pytest.mark.parametrize(
        ("router_type", "expected"),
        [
            pytest.param(RouterType.SMG, "sglang", id="smg"),
            pytest.param(RouterType.DYNAMO, "dynamo", id="dynamo"),
        ],
    )
    def test_serializes_smg_to_legacy_value_in_json(self, router_type: RouterType, expected: str):
        router = ReplicaGroupRouterConfig(type=router_type)
        assert router.model_dump(mode="json") == {"type": expected}
        assert router.model_dump_json() == f'{{"type":"{expected}"}}'
        assert ReplicaGroupRouterConfig.model_validate_json(router.model_dump_json()) == router

    def test_keeps_enum_in_python_dump(self):
        router = ReplicaGroupRouterConfig(type=RouterType.SMG)
        assert router.model_dump() == {"type": RouterType.SMG}
