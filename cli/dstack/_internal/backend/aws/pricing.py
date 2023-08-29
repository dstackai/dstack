from dstack._internal.backend.base.pricing import CatalogPricing


class AWSPricing(CatalogPricing):
    def __init__(self):
        super().__init__("aws.csv")
