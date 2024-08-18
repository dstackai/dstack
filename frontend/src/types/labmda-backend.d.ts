
declare interface ILambdaBackendValues {
    type: 'lambda',
    regions: TBackendValueField<string[]>,
}

declare interface IBackendLambda {
    type: 'lambda',
    creds: {
        api_key: string,
    },
    regions: string[],
}
