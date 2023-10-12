# ~/.dstack/server/config.yml

## YAML reference

#SCHEMA# dstack._internal.server.services.config.ServerConfig

#SCHEMA# dstack._internal.server.services.config.ProjectConfig
    overrides:
        backends:
            type: 'Union[AWSConfigInfoWithCreds, AzureConfigInfoWithCreds, GCPConfigInfoWithCreds, LambdaConfigInfoWithCreds]'

#SCHEMA# dstack._internal.core.models.backends.aws.AWSConfigInfoWithCreds

##SCHEMA# dstack._internal.core.models.backends.aws.AWSDefaultCreds

##SCHEMA# dstack._internal.core.models.backends.aws.AWSAccessKeyCreds

#SCHEMA# dstack._internal.core.models.backends.azure.AzureConfigInfoWithCreds

##SCHEMA# dstack._internal.core.models.backends.azure.AzureDefaultCreds

##SCHEMA# dstack._internal.core.models.backends.azure.AzureClientCreds

#SCHEMA# dstack._internal.core.models.backends.gcp.GCPConfigInfoWithCreds

##SCHEMA# dstack._internal.core.models.backends.gcp.GCPDefaultCreds

##SCHEMA# dstack._internal.core.models.backends.gcp.GCPServiceAccountCreds

#SCHEMA# dstack._internal.core.models.backends.lambdalabs.LambdaConfigInfoWithCreds

##SCHEMA# dstack._internal.core.models.backends.lambdalabs.LambdaAPIKeyCreds
