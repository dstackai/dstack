from pydantic_duality import DualBaseModel


# DualBaseModel creates two classes for the model:
# one with extra = "forbid" (CoreModel/CoreModel.__request__),
# and another with extra = "ignore" (CoreModel.__response__).
# This allows to use the same model both for a strict parsing of the user input and
# for a permissive parsing of the server responses.
class CoreModel(DualBaseModel):
    pass
