import enum


class Cloud(str, enum.Enum):
    aws = "aws"
    azure = "azure"
    gcp = "gcp"
    lambdalabs = "lambda"
