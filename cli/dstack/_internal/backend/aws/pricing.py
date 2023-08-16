import csv
import datetime
import json
from collections import defaultdict
from typing import Dict, Iterable, List, Optional

import boto3
import pkg_resources
from botocore.exceptions import ClientError, EndpointConnectionError

import dstack._internal.backend.aws.utils as aws_utils
from dstack._internal.backend.base.pricing import Pricing
from dstack._internal.core.instance import InstanceType


class AWSPricing(Pricing):
    """
    Required IAM policies:
      * ec2:DescribeSpotPriceHistory
    """

    def __init__(self, session: boto3.Session):
        super().__init__()
        self.session = session
        self.pricing_client = self.session.client("pricing", region_name="us-east-1")

    def _fetch_ondemand(self):
        pricing_path = pkg_resources.resource_filename(
            "dstack._internal.backend", "resources/aws_pricing_ondemand.csv"
        )
        with open(pricing_path, "r", newline="") as f:
            reader: Iterable[Dict[str, str]] = csv.DictReader(f)
            for row in reader:
                is_spot = {"True": True, "False": False}[row["spot"]]
                self.registry[row["instance_name"]][(row["location"], is_spot)] = float(
                    row["price"]
                )

    def _fetch_spot(self, instances: List[InstanceType]):
        regions = set(region for i in instances for region in i.available_regions)
        for region in regions:
            instance_types = [
                i.instance_name
                for i in instances
                if self._need_update(
                    f"spot-{i.instance_name}-{region}", ttl=4 * 60 * 60
                )  # 4 hours
            ]
            if not instance_types:
                continue
            try:
                client = aws_utils.get_ec2_client(self.session, region_name=region)
                pages = client.get_paginator("describe_spot_price_history").paginate(
                    Filters=[
                        {
                            "Name": "product-description",
                            "Values": ["Linux/UNIX"],
                        }
                    ],
                    # WARNING: using Filters["instance-type"] gives fewer results. Why?
                    InstanceTypes=instance_types,
                    StartTime=datetime.datetime.utcnow(),
                )
                instance_prices = defaultdict(list)
                for page in pages:
                    for item in page["SpotPriceHistory"]:
                        instance_prices[item["InstanceType"]].append(float(item["SpotPrice"]))
                for instance_type, zone_prices in instance_prices.items():
                    # we drop AZ information
                    self.registry[instance_type][(region, True)] = min(zone_prices)
            except (ClientError, EndpointConnectionError) as e:
                pass

    def fetch(self, instances: List[InstanceType], spot: Optional[bool]):
        if spot is not True:
            if self._need_update(f"ondemand"):
                self._fetch_ondemand()
        if spot is not False:
            self._fetch_spot(instances)
