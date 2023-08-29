from dstack._internal.backend.base.pricing import CatalogPricing


class AzurePricing(CatalogPricing):
    def __init__(self):
        super().__init__("azure.csv")
