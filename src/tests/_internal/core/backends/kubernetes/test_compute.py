from dstack._internal.core.backends.kubernetes.compute import _get_gpus_from_node_labels
from dstack._internal.core.models.instances import Gpu


class TestGetGPUsFromNodeLabels:
    def test_returns_no_gpus_if_no_labels(self):
        assert _get_gpus_from_node_labels({}) == []

    def test_returns_no_gpus_if_missing_labels(self):
        assert _get_gpus_from_node_labels({"nvidia.com/gpu.count": 1}) == []

    def test_returns_correct_memory_for_different_A100(self):
        assert _get_gpus_from_node_labels(
            {
                "nvidia.com/gpu.count": 1,
                "nvidia.com/gpu.product": "A100-SXM4-40GB",
            }
        ) == [Gpu(name="A100", memory_mib=40 * 1024)]
        assert _get_gpus_from_node_labels(
            {
                "nvidia.com/gpu.count": 1,
                "nvidia.com/gpu.product": "A100-SXM4-80GB",
            }
        ) == [Gpu(name="A100", memory_mib=80 * 1024)]
