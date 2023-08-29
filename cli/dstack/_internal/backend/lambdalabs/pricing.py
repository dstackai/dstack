from dstack._internal.backend.base.pricing import CatalogPricing


class LambdaPricing(CatalogPricing):
    def __init__(self):
        super().__init__("lambdalabs.csv")
