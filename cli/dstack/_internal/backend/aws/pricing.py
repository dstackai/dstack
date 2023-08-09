import datetime
import json
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

import dstack._internal.backend.aws.utils as aws_utils
from dstack._internal.backend.base.pricing import BasePricing
from dstack._internal.core.instance import InstanceType


class AWSPricing(BasePricing):
    """
    Required IAM policies:
      * pricing:GetProducts
      * ec2:DescribeSpotPriceHistory
    """

    def __init__(self, session: boto3.Session):
        super().__init__()
        self.session = session
        self.pricing_client = self.session.client("pricing")
        self.last_used: Dict[str, float] = {}

    def _fetch_ondemand(self, attributes: Dict[str, str]):
        def get_ondemand_price(terms: dict) -> Dict[str, str]:
            for _, term in terms["OnDemand"].items():
                for _, dim in term["priceDimensions"].items():
                    return dim["pricePerUnit"]

        # todo cache
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
            for item in page["PriceList"]:
                item = json.loads(item)
                attrs = item["product"]["attributes"]
                if "Usage" not in attrs["usagetype"] or attrs["tenancy"] == "Host":
                    continue
                price = get_ondemand_price(item["terms"])
                if "USD" in price:
                    self.cache[attrs["instanceType"]][(attrs["regionCode"], False)] = float(
                        price["USD"]
                    )

    def _fetch_spot(self, instance_type: str, regions: List[str]):
        for region in regions:
            try:
                client = aws_utils.get_ec2_client(self.session, region_name=region)
                # todo cache
                pages = client.get_paginator("describe_spot_price_history").paginate(
                    Filters=[
                        {
                            "Name": "product-description",
                            "Values": ["Linux/UNIX"],
                        }
                    ],
                    # WARNING: using Filters["instance-type"] gives fewer results. Why?
                    InstanceTypes=[instance_type],
                    StartTime=datetime.datetime.utcnow(),
                )
                prices = []
                for page in pages:
                    for item in page["SpotPriceHistory"]:
                        prices.append(float(item["SpotPrice"]))
                if prices:
                    # we drop AZ information
                    self.cache[instance_type][(region, True)] = min(prices)
            except (ClientError, EndpointConnectionError) as e:
                pass

    def fetch(self, instance: InstanceType, spot: Optional[bool]):
        self._fetch_ondemand(
            {
                "instanceType": instance.instance_name,
                "tenancy": "Shared",  # todo: is not valid for Dedicated VPC
                "operatingSystem": "Linux",
            }
        )
        if spot is not False:
            regions = list(
                set(
                    region
                    for region, _ in self.cache[instance.instance_name]
                    if self.region_match(instance.available_regions, region)
                )
            )
            self._fetch_spot(instance.instance_name, regions)
