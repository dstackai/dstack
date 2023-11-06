# ~/.dstack/server/config.yml

## YAML reference

#SCHEMA# dstack._internal.server.services.config.ServerConfig

#SCHEMA# dstack._internal.server.services.config.ProjectConfig
    overrides:
        backends:
            type: 'Union[AWSConfigInfoWithCreds, AzureConfigInfoWithCreds, GCPConfigInfoWithCreds, LambdaConfigInfoWithCreds, TensorDockConfigInfoWithCreds, VastAIConfigInfoWithCreds]'

#SCHEMA# dstack._internal.server.services.config.AWSConfig

##SCHEMA# dstack._internal.core.models.backends.aws.AWSDefaultCreds

##SCHEMA# dstack._internal.core.models.backends.aws.AWSAccessKeyCreds

#SCHEMA# dstack._internal.server.services.config.AzureConfig

##SCHEMA# dstack._internal.core.models.backends.azure.AzureDefaultCreds

##SCHEMA# dstack._internal.core.models.backends.azure.AzureClientCreds

#SCHEMA# dstack._internal.server.services.config.GCPConfig

##SCHEMA# dstack._internal.server.services.config.GCPDefaultCreds

##SCHEMA# dstack._internal.server.services.config.GCPServiceAccountCreds

#SCHEMA# dstack._internal.server.services.config.LambdaConfig

##SCHEMA# dstack._internal.core.models.backends.lambdalabs.LambdaAPIKeyCreds

#SCHEMA# dstack._internal.server.services.config.TensorDockConfig

##SCHEMA# dstack._internal.core.models.backends.tensordock.TensorDockAPIKeyCreds

#SCHEMA# dstack._internal.server.services.config.VastAIConfig

##SCHEMA# dstack._internal.core.models.backends.vastai.VastAIAPIKeyCreds
