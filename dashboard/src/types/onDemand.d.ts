declare type TPurchaseType = 'spot' | 'on-demand'

declare type TInstanceTypeName = string

declare interface IInstanceType {
    instance_type: TInstanceTypeName;
    purchase_types: TPurchaseType[];
}

declare interface IInstanceTypesRequestParams {
    region_name: IRegion['region_name'],
    purchase_type?: TPurchaseType
}

declare interface IRegion {
    location: string,
    name: string,
    title: string,
}

declare interface ISetLimitRequestParams {
    region_name: IRegion['name'],
    instance_type: TInstanceTypeName,
    maximum: number,
    purchase_type: TPurchaseType
}

declare interface IDeleteLimitRequestParams {
    region_name: IRegion['name'],
    instance_type: TInstanceTypeName,
    purchase_type: TPurchaseType
}

declare interface ILimit {
    region_name: IRegion['name'],
    instance_type: TInstanceTypeName,
    maximum: null | number,
    purchase_type: TPurchaseType,
    resources: IRunnerResources | null,
    availability_issues_at: IAvailabilityIssues['timestamp'],
    availability_issues_message: IAvailabilityIssues['message']
}

declare interface IDemandSettings {
    enabled: boolean,
    read_only: boolean,
}
