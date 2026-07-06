import gpuhunt
import pytest

from dstack._internal.core.backends.slurm.resources import GPUModel, parse_gres_gpu_count

NVIDIA = gpuhunt.AcceleratorVendor.NVIDIA
AMD = gpuhunt.AcceleratorVendor.AMD


class TestGPUModelStr:
    def test_nvidia(self):
        assert (
            str(GPUModel(vendor=NVIDIA, name="A100", memory_mib=80 * 1024)) == "nvidia:A100:80GB"
        )

    def test_amd(self):
        assert (
            str(GPUModel(vendor=AMD, name="MI300X", memory_mib=192 * 1024)) == "amd:MI300X:192GB"
        )

    def test_roundtrips_through_from_string(self):
        model = GPUModel(vendor=NVIDIA, name="A100", memory_mib=80 * 1024)
        assert GPUModel.from_string(str(model)) == model


class TestGPUModelFromString:
    def test_vendor_name_memory_uses_values_verbatim(self):
        # With vendor and memory both given, gpuhunt is bypassed, so an unknown name is accepted
        # and the name is kept verbatim (no space normalization).
        assert GPUModel.from_string("nvidia:Custom Accel:16GB") == GPUModel(
            vendor=NVIDIA, name="Custom Accel", memory_mib=16 * 1024
        )

    def test_name_only_looks_up_nvidia(self):
        assert GPUModel.from_string("H100") == GPUModel(
            vendor=NVIDIA, name="H100", memory_mib=80 * 1024
        )

    def test_name_only_looks_up_amd(self):
        assert GPUModel.from_string("MI300X") == GPUModel(
            vendor=AMD, name="MI300X", memory_mib=192 * 1024
        )

    def test_name_only_normalizes_spaces_for_lookup(self):
        assert GPUModel.from_string("RTX 4090") == GPUModel(
            vendor=NVIDIA, name="RTX4090", memory_mib=24 * 1024
        )

    def test_vendor_and_name(self):
        assert GPUModel.from_string("nvidia:H100") == GPUModel(
            vendor=NVIDIA, name="H100", memory_mib=80 * 1024
        )

    @pytest.mark.parametrize("memory_gb", [40, 80])
    def test_name_and_memory_disambiguates_variants(self, memory_gb: int):
        assert GPUModel.from_string(f"A100:{memory_gb}GB") == GPUModel(
            vendor=NVIDIA, name="A100", memory_mib=memory_gb * 1024
        )

    def test_memory_is_rounded_to_gib_for_matching(self):
        assert GPUModel.from_string("A100:80.4GB") == GPUModel(
            vendor=NVIDIA, name="A100", memory_mib=80 * 1024
        )

    def test_raises_when_no_gpu_matches_name(self):
        with pytest.raises(ValueError, match="No matching GPU model found"):
            GPUModel.from_string("ThisGpuDoesNotExist")

    def test_raises_when_multiple_gpus_match_name(self):
        with pytest.raises(ValueError, match="Multiple matching GPU models found"):
            GPUModel.from_string("A100")

    def test_raises_when_vendor_does_not_match(self):
        with pytest.raises(ValueError, match="No matching GPU model found"):
            GPUModel.from_string("amd:A100")

    def test_raises_when_memory_matches_no_variant(self):
        with pytest.raises(ValueError, match="No matching GPU model found"):
            GPUModel.from_string("A100:24GB")

    @pytest.mark.parametrize("s", ["", "   ", ":::", "a:b:c:d", "nvidia:A100:80GB:extra"])
    def test_raises_on_invalid_format(self, s: str):
        with pytest.raises(ValueError, match="Invalid format"):
            GPUModel.from_string(s)


class TestParseGresGpuCount:
    def test_count_only(self):
        assert parse_gres_gpu_count("gpu:8") == 8

    def test_type_and_count(self):
        assert parse_gres_gpu_count("gpu:tesla:2") == 2

    def test_count_with_socket_affinity(self):
        assert parse_gres_gpu_count("gpu:8(S:0)") == 8

    def test_type_and_count_with_socket_affinity(self):
        assert parse_gres_gpu_count("gpu:tesla:4(S:0-1)") == 4

    @pytest.mark.parametrize("gres", ["mps:200", "mem:1024", "gpu", ""])
    def test_returns_zero_for_non_gpu_gres(self, gres: str):
        assert parse_gres_gpu_count(gres) == 0

    @pytest.mark.parametrize("gres", ["gpu:tesla", "gpu:", "gpu:x(S:0)"])
    def test_raises_when_count_is_not_an_integer(self, gres: str):
        with pytest.raises(ValueError):
            parse_gres_gpu_count(gres)
