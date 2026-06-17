import logging
import sys
import time
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, TypeVar

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
    def from_namespace(args: Namespace) -> "CheckCommandArgs":
        return CheckCommandArgs(
            image_name=args.image_name,
            regions=args.regions or [],
            compartment_id=args.compartment_id,
        )


@dataclass
class DeletePublicationsCommandArgs:
    compartment_id: str
    regions: List[str]
    before: datetime
    name_contains: Optional[str]
    keep_latest: int
    yes: bool

    @classmethod
    def setup_parser(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--compartment", dest="compartment_id", required=True)
        parser.add_argument("--regions", metavar="REGION_NAME", nargs="*")
        _add_cleanup_filter_arguments(parser)
        parser.set_defaults(to_struct=cls.from_namespace, run_command=delete_publications_command)

    @staticmethod
    def from_namespace(args: Namespace) -> "DeletePublicationsCommandArgs":
        return DeletePublicationsCommandArgs(
            compartment_id=args.compartment_id,
            regions=args.regions or [],
            before=_parse_before(args.before),
            name_contains=args.name_contains,
            keep_latest=_validate_keep_latest(args.keep_latest),
            yes=args.yes,
        )


@dataclass
class DeleteImagesCommandArgs:
    compartment_id: str
    regions: List[str]
    before: datetime
    name_contains: Optional[str]
    keep_latest: int
    yes: bool

    @classmethod
    def setup_parser(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--compartment", dest="compartment_id", required=True)
        parser.add_argument("--regions", metavar="REGION_NAME", nargs="*")
        _add_cleanup_filter_arguments(parser)
        parser.set_defaults(to_struct=cls.from_namespace, run_command=delete_images_command)

    @staticmethod
    def from_namespace(args: Namespace) -> "DeleteImagesCommandArgs":
        return DeleteImagesCommandArgs(
            compartment_id=args.compartment_id,
            regions=args.regions or [],
            before=_parse_before(args.before),
            name_contains=args.name_contains,
            keep_latest=_validate_keep_latest(args.keep_latest),
            yes=args.yes,
        )


@dataclass
class DeleteBucketsCommandArgs:
    compartment_id: str
    regions: List[str]
    before: datetime
    name_contains: Optional[str]
    keep_latest: int
    yes: bool

    @classmethod
    def setup_parser(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--compartment", dest="compartment_id", required=True)
        parser.add_argument("--regions", metavar="REGION_NAME", nargs="*")
        _add_cleanup_filter_arguments(parser)
        parser.set_defaults(to_struct=cls.from_namespace, run_command=delete_buckets_command)

    @staticmethod
    def from_namespace(args: Namespace) -> "DeleteBucketsCommandArgs":
        return DeleteBucketsCommandArgs(
            compartment_id=args.compartment_id,
            regions=args.regions or [],
            before=_parse_before(args.before),
            name_contains=args.name_contains,
            keep_latest=_validate_keep_latest(args.keep_latest),
            yes=args.yes,
        )


def _add_cleanup_filter_arguments(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--before",
        required=True,
        metavar="YYYY-MM-DD",
        help="Delete resources created strictly before this date (UTC)",
    )
    parser.add_argument(
        "--name-contains",
        help="Only consider resources whose name contains this substring (case-insensitive)",
    )
    parser.add_argument(
        "--keep-latest",
        type=int,
        default=0,
        help="Always keep this many newest matching resources per region, "
        "regardless of --before (default: 0)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete (default: preview only)",
    )


def _parse_before(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ScriptError(f"Invalid --before date {value!r}, expected YYYY-MM-DD")


def _validate_keep_latest(value: int) -> int:
    if value < 0:
        raise ScriptError("--keep-latest must be >= 0")
    return value


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

    delete_publications_parser = subparsers.add_parser(
        name="delete-publications",
        description=(
            "Delete OCI Marketplace community publications (a.k.a. Community "
            "Applications) older than a date to free up the marketplace quota. "
            "Dry-run by default; pass --yes to actually delete. Run this before "
            "delete-images, since an image cannot be deleted while a publication "
            "still references it."
        ),
    )
    DeletePublicationsCommandArgs.setup_parser(delete_publications_parser)

    delete_images_parser = subparsers.add_parser(
        name="delete-images",
        description=(
            "Delete Custom Images older than a date in the given compartment and "
            "regions. Dry-run by default; pass --yes to actually delete."
        ),
    )
    DeleteImagesCommandArgs.setup_parser(delete_images_parser)

    delete_buckets_parser = subparsers.add_parser(
        name="delete-buckets",
        description=(
            "Delete Object Storage buckets older than a date in the given compartment "
            "and regions, along with their contents (objects, pre-authenticated "
            "requests, in-progress uploads). The copy command creates a bucket named "
            "after the image to transfer it between regions and normally deletes it; "
            "use this to clean up buckets left over by interrupted copies. "
            "Dry-run by default; pass --yes to actually delete."
        ),
    )
    DeleteBucketsCommandArgs.setup_parser(delete_buckets_parser)

    args = parser.parse_args()
    if not hasattr(args, "run_command"):
        parser.print_help()
        sys.exit(1)
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


def delete_publications_command(args: DeletePublicationsCommandArgs) -> None:
    region_clients = get_region_clients(required_regions=args.regions)
    regions_to_clean = args.regions or list(region_clients)
    total_deleted = 0

    for region in sorted(regions_to_clean):
        client = region_clients[region].marketplace_client
        publications = list_community_publications(args.compartment_id, client)
        publications = _filter_by_name(publications, lambda p: p.name, args.name_contains)
        keep, to_delete = _partition_for_deletion(
            publications, lambda p: p.time_created, args.before, args.keep_latest
        )
        _report_selection(region, "publications", keep, to_delete, lambda p: (p.name, p.id))

        if args.yes:
            for publication in to_delete:
                client.delete_publication(publication.id)
                logging.info(
                    "[%s] deleted publication %s (%s)", region, publication.name, publication.id
                )
                total_deleted += 1

    _report_outcome(args.yes, "publications", total_deleted)


def delete_images_command(args: DeleteImagesCommandArgs) -> None:
    region_clients = get_region_clients(required_regions=args.regions)
    regions_to_clean = args.regions or list(region_clients)
    total_deleted = 0

    for region in sorted(regions_to_clean):
        client = region_clients[region].compute_client
        images = list_compartment_images(args.compartment_id, client)
        images = _filter_by_name(images, lambda i: i.display_name, args.name_contains)
        keep, to_delete = _partition_for_deletion(
            images, lambda i: i.time_created, args.before, args.keep_latest
        )
        _report_selection(region, "images", keep, to_delete, lambda i: (i.display_name, i.id))

        if args.yes:
            for image in to_delete:
                client.delete_image(image.id)
                logging.info("[%s] deleted image %s (%s)", region, image.display_name, image.id)
                total_deleted += 1

    _report_outcome(args.yes, "images", total_deleted)


def delete_buckets_command(args: DeleteBucketsCommandArgs) -> None:
    region_clients = get_region_clients(required_regions=args.regions)
    regions_to_clean = args.regions or list(region_clients)
    total_deleted = 0

    for region in sorted(regions_to_clean):
        client = region_clients[region].object_storage_client
        namespace: str = client.get_namespace().data
        buckets = list_compartment_buckets(namespace, args.compartment_id, client)
        buckets = _filter_by_name(buckets, lambda b: b.name, args.name_contains)
        keep, to_delete = _partition_for_deletion(
            buckets, lambda b: b.time_created, args.before, args.keep_latest
        )
        _report_selection(region, "buckets", keep, to_delete, lambda b: (b.name, namespace))

        if args.yes:
            for bucket in to_delete:
                resources.delete_bucket(namespace, bucket.name, client)
                logging.info("[%s] deleted bucket %s", region, bucket.name)
                total_deleted += 1

    _report_outcome(args.yes, "buckets", total_deleted)


def list_community_publications(
    compartment_id: str, client: oci.marketplace.MarketplaceClient
) -> List[oci.marketplace.models.PublicationSummary]:
    """
    List community publications (a.k.a. "Community Applications") created in
    `compartment_id`. These are the publisher-side counterparts of marketplace
    listings and count against the marketplace "Community Applications" quota.
    """
    return list(
        resources.chain_paginated_responses(
            client.list_publications,
            compartment_id=compartment_id,
            listing_type=oci.marketplace.models.PublicationSummary.LISTING_TYPE_COMMUNITY,
        )
    )


def list_compartment_images(
    compartment_id: str, client: oci.core.ComputeClient
) -> List[oci.core.models.Image]:
    """
    List Custom Images owned by `compartment_id`. `list_images` also returns
    Oracle platform images (with no compartment), which must never be deleted,
    so they are filtered out here.
    """
    images = resources.chain_paginated_responses(client.list_images, compartment_id=compartment_id)
    return [image for image in images if image.compartment_id == compartment_id]


def list_compartment_buckets(
    namespace: str, compartment_id: str, client: oci.object_storage.ObjectStorageClient
) -> List[oci.object_storage.models.BucketSummary]:
    return list(
        resources.chain_paginated_responses(
            client.list_buckets, namespace_name=namespace, compartment_id=compartment_id
        )
    )


T = TypeVar("T")


def _filter_by_name(
    items: Iterable[T], get_name: Callable[[T], str], name_contains: Optional[str]
) -> List[T]:
    if not name_contains:
        return list(items)
    needle = name_contains.lower()
    return [item for item in items if needle in get_name(item).lower()]


def _partition_for_deletion(
    items: Iterable[T],
    get_time: Callable[[T], datetime],
    before: datetime,
    keep_latest: int,
) -> Tuple[List[T], List[T]]:
    # Sort newest first so --keep-latest preserves the most recent resources.
    ordered = sorted(items, key=get_time, reverse=True)
    keep, to_delete = [], []
    for index, item in enumerate(ordered):
        if index < keep_latest or get_time(item) >= before:
            keep.append(item)
        else:
            to_delete.append(item)
    return keep, to_delete


def _report_selection(
    region: str,
    kind: str,
    keep: Sequence[T],
    to_delete: Sequence[T],
    describe: Callable[[T], Tuple[str, str]],
) -> None:
    logging.info(
        "[%s] %d matching %s: %d to delete, %d to keep",
        region,
        len(keep) + len(to_delete),
        kind,
        len(to_delete),
        len(keep),
    )
    for item in keep:
        name, ocid = describe(item)
        logging.info("[%s]   KEEP   %s (%s)", region, name, ocid)
    for item in to_delete:
        name, ocid = describe(item)
        logging.info("[%s]   DELETE %s (%s)", region, name, ocid)


def _report_outcome(deleted_for_real: bool, kind: str, total_deleted: int) -> None:
    if not deleted_for_real:
        logging.info("Preview only. Re-run with --yes to delete the %s.", kind)
    else:
        logging.info("Deleted %d %s.", total_deleted, kind)


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
