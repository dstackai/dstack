import datetime
import json
from collections import defaultdict
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

import dstack._internal.backend.aws.utils as aws_utils
from dstack._internal.backend.base.pricing import Pricing
from dstack._internal.core.instance import InstanceType


class AWSPricing(Pricing):
    """
    Required IAM policies:
      * pricing:GetProducts
      * ec2:DescribeSpotPriceHistory
    """

    def __init__(self, session: boto3.Session):
        super().__init__()
        self.session = session
        self.pricing_client = self.session.client("pricing")

    def _fetch_ondemand(self, attributes: Dict[str, str]):
        def get_ondemand_price(terms: dict) -> Dict[str, str]:
            for _, term in terms["OnDemand"].items():
                for _, dim in term["priceDimensions"].items():
                    return dim["pricePerUnit"]

        pages = self.pricing_client.get_paginator("get_products").paginate(
            ServiceCode="AmazonEC2",
            Filters=[
                {
                    "Type": "TERM_MATCH",
                    "Field": key,
                    "Value": value,
                }
                for key, value in attributes.items()
            ],
        )
        for page in pages:
            for raw_item in page["PriceList"]:
                item = json.loads(raw_item)
                attrs = item["product"]["attributes"]
                if "Usage" not in attrs["usagetype"] or attrs["tenancy"] == "Host":
                    continue
                if "OnDemand" not in item["terms"]:
                    continue
                price = get_ondemand_price(item["terms"])
                if "USD" in price:
                    self.registry[attrs["instanceType"]][(attrs["regionCode"], False)] = float(
                        price["USD"]
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
        for instance in instances:
            if self._need_update(f"ondemand-{instance.instance_name}"):
                self._fetch_ondemand(
                    {
                        "instanceType": instance.instance_name,
                        "tenancy": "Shared",  # todo: is not valid for Dedicated VPC
                        "operatingSystem": "Linux",
                    }
                )
        if spot is not False:
            self._fetch_spot(instances)
