import logging
import sys
import time
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Mapping

import oci
from oci.object_storage.models import Bucket
from oci.work_requests.models import WorkRequest

from dstack._internal.core.backends.oci import resources
from dstack._internal.core.backends.oci.models import OCIDefaultCreds
from dstack._internal.core.backends.oci.region import (
    OCIRegionClient,
    get_subscribed_regions,
    make_region_clients_map,
)

WORK_REQUEST_UPDATE_INTERVAL_SECS = 15
MAX_IMAGE_IMPORT_OR_EXPORT_SECS = 40 * 60
PRE_AUTHENTICATED_REQUEST_LIFETIME = timedelta(hours=1.5)
ONGOING_WR_STATUSES = (WorkRequest.STATUS_ACCEPTED, WorkRequest.STATUS_IN_PROGRESS)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


class ScriptError(Exception):
    pass


@dataclass
class CopyCommandArgs:
    image_name: str
    source_region: str
    target_regions: List[str]
    compartment_id: str

    @classmethod
    def setup_parser(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--image", dest="image_name", required=True)
        parser.add_argument(
            "--from", dest="source_region", metavar="SOURCE_REGION_NAME", required=True
        )
        parser.add_argument("--to", dest="target_regions", metavar="TARGET_REGION_NAME", nargs="*")
        parser.add_argument("--compartment", dest="compartment_id", required=True)
        parser.set_defaults(to_struct=cls.from_namespace, run_command=copy_command)

    @staticmethod
    def from_namespace(args: Namespace) -> "CopyCommandArgs":
        return CopyCommandArgs(
            image_name=args.image_name,
            source_region=args.source_region,
            target_regions=args.target_regions or [],
            compartment_id=args.compartment_id,
        )


@dataclass
class PublishCommandArgs:
    image_name: str
    regions: List[str]
    compartment_id: str
    version: str
    short_description: str
    os_name: str
    eula_text: str
    contact_name: str
    contact_email: str

    @classmethod
    def setup_parser(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--image", dest="image_name", required=True)
        parser.add_argument("--regions", metavar="REGION_NAME", nargs="*")
        parser.add_argument("--compartment", dest="compartment_id", required=True)
        parser.add_argument("--version", required=True)
        parser.add_argument("--description", dest="short_description", required=True)
        parser.add_argument("--os", dest="os_name", metavar="OPERATING_SYSTEM_NAME", required=True)
        parser.add_argument(
            "--eula",
            dest="eula_text",
            metavar="END_USER_LICENSE_AGREEMENT_TEXT",
            default="I agree to use this software at my own risk.",
        )
        parser.add_argument("--contact-name", required=True)
        parser.add_argument("--contact-email", required=True)
        parser.set_defaults(to_struct=cls.from_namespace, run_command=publish_command)

    @staticmethod
    def from_namespace(args: Namespace) -> "PublishCommandArgs":
        return PublishCommandArgs(
            image_name=args.image_name,
            regions=args.regions or [],
            compartment_id=args.compartment_id,
            version=args.version,
            short_description=args.short_description,
            os_name=args.os_name,
            eula_text=args.eula_text,
            contact_name=args.contact_name,
            contact_email=args.contact_email,
        )


@dataclass
class CheckCommandArgs:
    image_name: str
    regions: List[str]
    compartment_id: str

    @classmethod
    def setup_parser(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--image", dest="image_name", required=True)
        parser.add_argument("--regions", metavar="REGION_NAME", nargs="*")
        parser.add_argument("--compartment", dest="compartment_id", required=True)
        parser.set_defaults(to_struct=cls.from_namespace, run_command=check_command)

    @staticmethod
    def from_namespace(args: Namespace) -> "PublishCommandArgs":
        return CheckCommandArgs(
            image_name=args.image_name,
            regions=args.regions or [],
            compartment_id=args.compartment_id,
        )


def main() -> None:
    parser = ArgumentParser(description="Tools for delivering OCI images")
    subparsers = parser.add_subparsers()

    copy_parser = subparsers.add_parser(
        name="copy",
        description=(
            "Copy Custom Image from source region to all subscribed regions or "
            "specified target regions. This is done by exporting to and importing from "
            "a Storage Bucket."
        ),
    )
    CopyCommandArgs.setup_parser(copy_parser)

    publish_parser = subparsers.add_parser(
        name="publish",
        description=(
            "Publish Custom Image in OCI Marketplace in all subscribed regions or in "
            "specified regions. The image must already exist in these regions."
        ),
    )
    PublishCommandArgs.setup_parser(publish_parser)

    check_parser = subparsers.add_parser(
        name="check",
        description=(
            "Check that Custom Image is published in OCI Marketplace in all subscribed "
            "regions or in specified regions."
        ),
    )
    CheckCommandArgs.setup_parser(check_parser)

    args = parser.parse_args()
    args.run_command(args.to_struct(args))


def copy_command(args: CopyCommandArgs) -> None:
    region_clients = get_region_clients(
        required_regions=args.target_regions + [args.source_region]
    )
    source_region = region_clients[args.source_region]

    namespace: str = source_region.object_storage_client.get_namespace().data
    bucket = resources.get_or_create_bucket(
        namespace, args.image_name, args.compartment_id, source_region.object_storage_client
    )
    export_image_to_bucket(args.image_name, bucket, args.compartment_id, source_region)
    import_image_from_bucket_in_target_regions(
        args.image_name,
        bucket,
        args.compartment_id,
        source_region,
        args.target_regions or list(region_clients),
        region_clients,
    )

    resources.delete_bucket(namespace, bucket.name, source_region.object_storage_client)


def publish_command(args: PublishCommandArgs) -> None:
    region_clients = get_region_clients(required_regions=args.regions)
    regions_for_publishing = args.regions or list(region_clients)
    images = find_image_in_regions(
        args.image_name, args.compartment_id, regions_for_publishing, region_clients
    )

    for i, region_name in enumerate(regions_for_publishing, start=1):
        resources.publish_image_in_marketplace(
            name=args.image_name,
            version=args.version,
            short_description=args.short_description,
            os_name=args.os_name,
            eula_text=args.eula_text,
            contact_name=args.contact_name,
            contact_email=args.contact_email,
            image_id=images[region_name].id,
            compartment_id=args.compartment_id,
            client=region_clients[region_name].marketplace_client,
        )
        logging.info("Submitted in %s (%d/%d)", region_name, i, len(regions_for_publishing))

    logging.info("Submitted image %s in regions: %s", args.image_name, regions_for_publishing)
    logging.info(
        "The publications will now go through OCI's review process that may take a few hours. "
        "The publications will be unavailable until the review finishes. "
        "Use `python oci_image_tools.py check` to check publication statuses."
    )


def check_command(args: CheckCommandArgs) -> None:
    region_clients = get_region_clients(required_regions=args.regions)
    regions_to_check = args.regions or list(region_clients)
    some_not_published = False

    for region in sorted(regions_to_check):
        if not resources.list_marketplace_listings(
            args.image_name, region_clients[region].marketplace_client
        ):
            some_not_published = True
            status = "Not published"
        else:
            status = "Published"
        logging.info("%24s: %s", region, status)

    if some_not_published:
        raise ScriptError(
            f"Image {args.image_name} is not published or is still under review in some regions. "
            "Check the review status by choosing the correct region and compartment here: "
            "https://cloud.oracle.com/marketplace/community-images"
        )


def get_region_clients(
    required_regions: Iterable[str] = frozenset(),
) -> Dict[str, OCIRegionClient]:
    """
    Returns OCIRegionClient for every subscribed region and checks that all
    `required_regions` are included
    """

    creds = OCIDefaultCreds()
    subscribed_regions = get_subscribed_regions(creds).names
    if invalid_regions := set(required_regions) - subscribed_regions:
        raise ScriptError(
            f"Specified region names do not exist or are not subscribed to: {invalid_regions}"
        )
    return make_region_clients_map(subscribed_regions, creds)


def export_image_to_bucket(
    image_name: str, bucket: Bucket, compartment_id: str, region: OCIRegionClient
) -> None:
    image = resources.find_image(image_name, compartment_id, region.compute_client)
    if image is None:
        raise ScriptError(
            f"Image {image_name} not found in region {region.name}, compartment {compartment_id}"
        )

    work_request_id = resources.export_image_to_bucket(
        image_id=image.id,
        storage_namespace=bucket.namespace,
        bucket_name=bucket.name,
        object_name=image.display_name,
        client=region.compute_client,
    )
    wait_for_image_export(image.display_name, work_request_id, region.work_request_client)


def wait_for_image_export(
    image_name: str,
    work_request_id: str,
    client: oci.work_requests.WorkRequestClient,
) -> None:
    time_start = time.time()
    work_request: WorkRequest = client.get_work_request(work_request_id).data

    while work_request.status in ONGOING_WR_STATUSES:
        if time.time() - time_start > MAX_IMAGE_IMPORT_OR_EXPORT_SECS:
            raise ScriptError(
                f"Image export is taking more than {MAX_IMAGE_IMPORT_OR_EXPORT_SECS} seconds. "
                "Giving up."
            )
        logging.info(
            "Exporting image %s: %.0f%% complete", image_name, work_request.percent_complete
        )
        time.sleep(WORK_REQUEST_UPDATE_INTERVAL_SECS)
        work_request = client.get_work_request(work_request_id).data

    if work_request.status != work_request.STATUS_SUCCEEDED:
        raise ScriptError(f"Failed exporting image {image_name}: status {work_request.status}")

    logging.info("Successfully exported image %s", image_name)


def import_image_from_bucket_in_target_regions(
    image_name: str,
    bucket: Bucket,
    compartment_id: str,
    source_region: OCIRegionClient,
    target_region_names: Iterable[str],
    regions: Mapping[str, OCIRegionClient],
) -> None:
    """
    Imports `image_name` from `bucket` to all `target_regions` except `source_region`.
    It is assumed that `source_region` already has the image.
    """

    pre_authenticated_request = resources.create_pre_authenticated_request(
        name=f"par-{int(time.time())}-{image_name}",
        namespace=bucket.namespace,
        bucket_name=bucket.name,
        object_name=image_name,
        time_expires=datetime.now() + PRE_AUTHENTICATED_REQUEST_LIFETIME,
        client=source_region.object_storage_client,
    )

    work_requests: Dict[str, WorkRequest] = {}
    for region_name in target_region_names:
        if region_name == source_region.name:
            continue
        region_client = regions[region_name]
        work_request_id = resources.import_image_from_uri(
            image_name,
            pre_authenticated_request.full_path,
            compartment_id,
            region_client.compute_client,
        )
        work_requests[region_name] = region_client.work_request_client.get_work_request(
            work_request_id
        ).data

    work_requests = wait_for_images_import(image_name, work_requests, regions)
    check_images_import_statuses(image_name, work_requests, regions)


def wait_for_images_import(
    image_name: str,
    work_requests: Mapping[str, WorkRequest],
    regions: Mapping[str, OCIRegionClient],
) -> Dict[str, WorkRequest]:
    time_start = time.time()
    work_requests = dict(work_requests)

    while any(wr.status in ONGOING_WR_STATUSES for wr in work_requests.values()):
        if time.time() - time_start > MAX_IMAGE_IMPORT_OR_EXPORT_SECS:
            raise ScriptError(
                f"Images import is taking more than {MAX_IMAGE_IMPORT_OR_EXPORT_SECS} seconds. "
                "Giving up."
            )

        report = "\n".join(
            f"{region_name:>24}: {work_request.percent_complete:.0f}% complete"
            for region_name, work_request in work_requests.items()
        )
        logging.info("Importing image %s:\n%s", image_name, report)
        time.sleep(WORK_REQUEST_UPDATE_INTERVAL_SECS)

        for region_name, work_request in work_requests.items():
            if work_request.status in ONGOING_WR_STATUSES:
                work_requests[region_name] = (
                    regions[region_name].work_request_client.get_work_request(work_request.id).data
                )

    return work_requests


def check_images_import_statuses(
    image_name: str,
    work_requests: Mapping[str, WorkRequest],
    regions: Mapping[str, OCIRegionClient],
) -> None:
    successful_regions = []
    failed_regions = []

    for region_name, work_request in work_requests.items():
        if work_request.status == WorkRequest.STATUS_SUCCEEDED:
            successful_regions.append(region_name)
        else:
            failed_regions.append(region_name)
            errors = resources.list_work_request_errors(
                work_request.id, regions[region_name].work_request_client
            )
            logging.error(
                "Failed importing image %s in %s. Status: %s. Errors: %s",
                image_name,
                region_name,
                work_request.status,
                [e.message for e in errors],
            )

    if successful_regions:
        logging.info(
            "Successfully imported image %s in %s", image_name, ", ".join(successful_regions)
        )
    if failed_regions:
        raise ScriptError(f"Importing image {image_name} failed in regions: {failed_regions}")


def find_image_in_regions(
    image_name: str,
    compartment_id: str,
    regions_to_search: Iterable[str],
    region_clients: Mapping[str, OCIRegionClient],
) -> Mapping[str, oci.core.models.Image]:
    images = {}
    for region_name in regions_to_search:
        image = resources.find_image(
            image_name, compartment_id, region_clients[region_name].compute_client
        )
        if image is None:
            raise ScriptError(
                f"Image {image_name} does not exist is {region_name}, compartment {compartment_id}"
            )
        images[region_name] = image
    return images


if __name__ == "__main__":
    try:
        main()
    except ScriptError as e:
        logging.error(e)
        sys.exit(1)
