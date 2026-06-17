"""
Tools for managing dstack AWS AMIs across regions.

dstack publishes public AMIs (see scripts/packer/aws-image.json) to all regions
listed in scripts/packer/aws-vars-prod.json. Over time these accumulate and hit
the per-region AMI service quota (the AWS error looks like "the maximum number of
AMIs has been reached"). This script helps to:

  1. request-quota  Request a service quota increase across regions (e.g. the EC2
                    "AMIs" / "Public AMIs" quota).
  2. list-quotas    Discover quota codes and/or quota names
                    (e.g. search for "AMI") to use with request-quota.
  3. delete-amis    Deregister AMIs older than a date and delete their snapshots.
                    Dry-run by default — pass --yes to actually delete.
"""

import logging
import sys
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import boto3

# Regions dstack copies AMIs to, kept in sync with scripts/packer/aws-vars-prod.json.
PROD_REGIONS = [
    "us-east-2",
    "us-east-1",
    "us-west-1",
    "us-west-2",
    "ca-central-1",
    "eu-central-1",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-north-1",
    "ap-southeast-1",
]

# Default name prefix of dstack AMIs (e.g. dstack-0.18, dstack-cuda-0.18).
DEFAULT_NAME_PREFIX = "dstack-"

EC2_SERVICE_CODE = "ec2"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("aws_image_tools")


class ScriptError(Exception):
    pass


@dataclass
class RequestQuotaCommandArgs:
    regions: List[str]
    service_code: str
    quota_code: str
    value: float
    yes: bool

    @classmethod
    def setup_parser(cls, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--regions",
            metavar="REGION",
            nargs="*",
            help="Regions to request the increase in (default: dstack prod regions)",
        )
        parser.add_argument("--service-code", default=EC2_SERVICE_CODE)
        parser.add_argument(
            "--quota-code",
            required=True,
            help="Quota code, e.g. L-0E3CBAB9 (same across regions; find it with list-quotas)",
        )
        parser.add_argument("--value", type=float, required=True, help="Desired new quota value")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Actually submit the requests (default: preview only)",
        )
        parser.set_defaults(to_struct=cls.from_namespace, run_command=request_quota_command)

    @staticmethod
    def from_namespace(args: Namespace) -> "RequestQuotaCommandArgs":
        return RequestQuotaCommandArgs(
            regions=args.regions or list(PROD_REGIONS),
            service_code=args.service_code,
            quota_code=args.quota_code,
            value=args.value,
            yes=args.yes,
        )


@dataclass
class ListQuotasCommandArgs:
    region: str
    service_code: str
    search: Optional[str]

    @classmethod
    def setup_parser(cls, parser: ArgumentParser) -> None:
        parser.add_argument("--region", default=PROD_REGIONS[0], help="Region to list quotas in")
        parser.add_argument("--service-code", default=EC2_SERVICE_CODE)
        parser.add_argument("--search", help="Case-insensitive substring to filter quota names by")
        parser.set_defaults(to_struct=cls.from_namespace, run_command=list_quotas_command)

    @staticmethod
    def from_namespace(args: Namespace) -> "ListQuotasCommandArgs":
        return ListQuotasCommandArgs(
            region=args.region,
            service_code=args.service_code,
            search=args.search,
        )


@dataclass
class DeleteAmisCommandArgs:
    regions: List[str]
    before: datetime
    name_prefix: str
    name_contains: Optional[str]
    keep_latest: int
    yes: bool

    @classmethod
    def setup_parser(cls, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--regions",
            metavar="REGION",
            nargs="*",
            help="Regions to delete AMIs in (default: dstack prod regions)",
        )
        parser.add_argument(
            "--before",
            required=True,
            metavar="YYYY-MM-DD",
            help="Delete AMIs created strictly before this date (UTC)",
        )
        parser.add_argument(
            "--name-prefix",
            default=DEFAULT_NAME_PREFIX,
            help=f"Only consider AMIs whose name starts with this (default: {DEFAULT_NAME_PREFIX!r})",
        )
        parser.add_argument(
            "--name-contains",
            help="Further restrict to AMIs whose name contains this substring "
            "(case-insensitive), e.g. a version like 0.18",
        )
        parser.add_argument(
            "--keep-latest",
            type=int,
            default=0,
            help="Always keep this many newest matching AMIs per region, "
            "regardless of --before (default: 0)",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Actually deregister AMIs and delete snapshots (default: preview only)",
        )
        parser.set_defaults(to_struct=cls.from_namespace, run_command=delete_amis_command)

    @staticmethod
    def from_namespace(args: Namespace) -> "DeleteAmisCommandArgs":
        try:
            before = datetime.strptime(args.before, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise ScriptError(f"Invalid --before date {args.before!r}, expected YYYY-MM-DD")
        if args.keep_latest < 0:
            raise ScriptError("--keep-latest must be >= 0")
        return DeleteAmisCommandArgs(
            regions=args.regions or list(PROD_REGIONS),
            before=before,
            name_prefix=args.name_prefix,
            name_contains=args.name_contains,
            keep_latest=args.keep_latest,
            yes=args.yes,
        )


def main() -> None:
    parser = ArgumentParser(description="Tools for managing dstack AWS AMIs")
    subparsers = parser.add_subparsers()

    request_quota_parser = subparsers.add_parser(
        name="request-quota",
        description="Request a service quota increase across regions.",
    )
    RequestQuotaCommandArgs.setup_parser(request_quota_parser)

    list_quotas_parser = subparsers.add_parser(
        name="list-quotas",
        description="List service quotas (and their codes) in a region.",
    )
    ListQuotasCommandArgs.setup_parser(list_quotas_parser)

    delete_amis_parser = subparsers.add_parser(
        name="delete-amis",
        description=(
            "Deregister AMIs older than a date and delete their snapshots. "
            "Dry-run by default; pass --yes to actually delete."
        ),
    )
    DeleteAmisCommandArgs.setup_parser(delete_amis_parser)

    args = parser.parse_args()
    if not hasattr(args, "run_command"):
        parser.print_help()
        sys.exit(1)
    try:
        args.run_command(args.to_struct(args))
    except ScriptError as e:
        logger.error("%s", e)
        sys.exit(1)


def request_quota_command(args: RequestQuotaCommandArgs) -> None:
    failed = False
    quota_code = args.quota_code
    for region in args.regions:
        client = boto3.client("service-quotas", region_name=region)
        current = _get_quota_value(client, args.service_code, quota_code)
        if current is not None and current >= args.value:
            logger.info(
                "[%s] %s already at %g >= %g, skipping",
                region,
                quota_code,
                current,
                args.value,
            )
            continue

        pending = _get_pending_request_value(client, args.service_code, quota_code)
        if pending is not None and pending >= args.value:
            logger.info(
                "[%s] %s already has a pending request for %g, skipping",
                region,
                quota_code,
                pending,
            )
            continue

        if not args.yes:
            logger.info(
                "[%s] would request %s increase to %g (current: %s)",
                region,
                quota_code,
                args.value,
                "unknown" if current is None else f"{current:g}",
            )
            continue

        try:
            client.request_service_quota_increase(
                ServiceCode=args.service_code,
                QuotaCode=quota_code,
                DesiredValue=args.value,
            )
            logger.info("[%s] requested %s increase to %g", region, quota_code, args.value)
        except Exception as e:
            logger.error("[%s] failed to request %s increase: %s", region, quota_code, e)
            failed = True

    if not args.yes:
        logger.info("Preview only. Re-run with --yes to submit the requests.")
    if failed:
        raise ScriptError("Some quota requests failed or were skipped")


def _get_quota_value(client, service_code: str, quota_code: str) -> Optional[float]:
    try:
        resp = client.get_service_quota(ServiceCode=service_code, QuotaCode=quota_code)
        return resp["Quota"]["Value"]
    except Exception:
        return None


def _get_pending_request_value(client, service_code: str, quota_code: str) -> Optional[float]:
    try:
        paginator = client.get_paginator("list_requested_service_quota_change_history_by_quota")
        latest_value = None
        for page in paginator.paginate(ServiceCode=service_code, QuotaCode=quota_code):
            for req in page["RequestedQuotas"]:
                if req["Status"] in ("PENDING", "CASE_OPENED"):
                    value = req["DesiredValue"]
                    if latest_value is None or value > latest_value:
                        latest_value = value
        return latest_value
    except Exception:
        return None


def list_quotas_command(args: ListQuotasCommandArgs) -> None:
    client = boto3.client("service-quotas", region_name=args.region)
    needle = args.search.lower() if args.search else None
    paginator = client.get_paginator("list_service_quotas")
    rows = []
    for page in paginator.paginate(ServiceCode=args.service_code):
        for quota in page["Quotas"]:
            if needle and needle not in quota["QuotaName"].lower():
                continue
            rows.append((quota["QuotaCode"], quota["Value"], quota["QuotaName"]))
    rows.sort(key=lambda r: r[2])
    if not rows:
        logger.info("No quotas found matching the filter.")
        return
    print(f"{'QUOTA CODE':<16} {'VALUE':>10}  NAME")
    for code, value, name in rows:
        print(f"{code:<16} {value:>10g}  {name}")


def delete_amis_command(args: DeleteAmisCommandArgs) -> None:
    total_deleted = 0
    for region in args.regions:
        ec2 = boto3.client("ec2", region_name=region)
        images = _find_self_owned_images(ec2, args.name_prefix, args.name_contains)
        # Sort newest first so --keep-latest preserves the most recent images.
        images.sort(key=lambda img: img["_created"], reverse=True)

        to_delete = []
        for index, image in enumerate(images):
            if index < args.keep_latest:
                continue
            if image["_created"] < args.before:
                to_delete.append(image)

        keep = [img for img in images if img not in to_delete]
        logger.info(
            "[%s] %d matching AMIs: %d to delete, %d to keep",
            region,
            len(images),
            len(to_delete),
            len(keep),
        )
        for image in keep:
            logger.info(
                "[%s]   KEEP   %s %s (%s)",
                region,
                image["ImageId"],
                image["Name"],
                image["CreationDate"],
            )
        for image in to_delete:
            snapshot_ids = _image_snapshot_ids(image)
            logger.info(
                "[%s]   DELETE %s %s (%s) snapshots=%s",
                region,
                image["ImageId"],
                image["Name"],
                image["CreationDate"],
                ",".join(snapshot_ids) or "none",
            )
            if args.yes:
                _deregister_image(ec2, region, image, snapshot_ids)
                total_deleted += 1

    if not args.yes:
        logger.info("Preview only. Re-run with --yes to deregister AMIs and delete snapshots.")
    else:
        logger.info("Deleted %d AMIs.", total_deleted)


def _find_self_owned_images(ec2, name_prefix: str, name_contains: Optional[str]) -> List[dict]:
    resp = ec2.describe_images(
        Owners=["self"],
        Filters=[{"Name": "name", "Values": [f"{name_prefix}*"]}],
    )
    images = resp["Images"]
    if name_contains:
        needle = name_contains.lower()
        images = [img for img in images if needle in img["Name"].lower()]
    for image in images:
        image["_created"] = datetime.strptime(
            image["CreationDate"], "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=timezone.utc)
    return images


def _image_snapshot_ids(image: dict) -> List[str]:
    snapshot_ids = []
    for mapping in image.get("BlockDeviceMappings", []):
        ebs = mapping.get("Ebs")
        if ebs and ebs.get("SnapshotId"):
            snapshot_ids.append(ebs["SnapshotId"])
    return snapshot_ids


def _deregister_image(ec2, region: str, image: dict, snapshot_ids: List[str]) -> None:
    try:
        ec2.deregister_image(ImageId=image["ImageId"])
        logger.info("[%s] deregistered %s", region, image["ImageId"])
    except Exception as e:
        logger.error("[%s] failed to deregister %s: %s", region, image["ImageId"], e)
        return
    for snapshot_id in snapshot_ids:
        try:
            ec2.delete_snapshot(SnapshotId=snapshot_id)
            logger.info("[%s] deleted snapshot %s", region, snapshot_id)
        except Exception as e:
            logger.error("[%s] failed to delete snapshot %s: %s", region, snapshot_id, e)


if __name__ == "__main__":
    main()
