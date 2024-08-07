declare type TBackendType = 'aws' | 'gcp' | 'azure' | 'lambda' | 'local' | 'dstack';

declare type TBackendValueField<TSelectedType = string, TValuesType = { value: string, label: string}[]> = {
    selected?: TSelectedType,
    values: TValuesType
} | null;

declare type TBackendValuesResponse = IAwsBackendValues & IAzureBackendValues & IGCPBackendValues & ILambdaBackendValues

declare interface IBackendLocal {
    type: 'local',
    path: string
}
declare interface IBackendDstack {
    type: 'dstack',
    path: string
}

declare type TBackendConfig = IBackendAWS | IBackendAzure | IBackendGCP | IBackendLambda | IBackendLocal | IBackendDstack

declare interface IBackendConfigYaml {
    config_yaml: string,
}

declare interface IProjectBackend {
    name: string
    config: TBackendConfig
}
