from unittest.mock import MagicMock, patch

from dstack._internal.core.backends.oci.region import OCIRegionClient

CREDS_TENANCY = "ocid1.tenancy.oc1..credentials"
OTHER_TENANCY_COMPARTMENT = "ocid1.compartment.oc1..shared-in-from-another-tenancy"


def make_region_client() -> OCIRegionClient:
    return OCIRegionClient(
        {
            "tenancy": CREDS_TENANCY,
            "region": "us-phoenix-1",
            "user": "ocid1.user.oc1..aaaa",
            "fingerprint": "00:11:22",
            "key_file": "/dev/null",
        }
    )


class TestAvailabilityDomainsIn:
    def test_resolves_domains_from_the_compartment_not_the_credentials(self):
        region = make_region_client()
        identity_client = MagicMock()
        with patch.object(
            OCIRegionClient, "identity_client", new_callable=lambda: identity_client
        ):
            region.availability_domains_in(OTHER_TENANCY_COMPARTMENT)

        identity_client.list_availability_domains.assert_called_once_with(
            OTHER_TENANCY_COMPARTMENT
        )

    def test_availability_domains_defaults_to_the_credentials_tenancy(self):
        region = make_region_client()
        identity_client = MagicMock()
        with patch.object(
            OCIRegionClient, "identity_client", new_callable=lambda: identity_client
        ):
            region.availability_domains

        identity_client.list_availability_domains.assert_called_once_with(CREDS_TENANCY)

    def test_result_is_cached_per_compartment(self):
        region = make_region_client()
        identity_client = MagicMock()
        with patch.object(
            OCIRegionClient, "identity_client", new_callable=lambda: identity_client
        ):
            region.availability_domains_in(OTHER_TENANCY_COMPARTMENT)
            region.availability_domains_in(OTHER_TENANCY_COMPARTMENT)
            region.availability_domains_in(CREDS_TENANCY)

        assert identity_client.list_availability_domains.call_count == 2
