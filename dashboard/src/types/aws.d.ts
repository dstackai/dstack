declare interface AWSCredentials {
    region: string;
    accessKeyId: string;
    secretAccessKey: string;
}

declare interface IAWSEvent {
    eventId: string,
    ingestionTime: number
    logStreamName: string
    message: string,
    timestamp: number
}

declare interface IAWSFilterLogEventsParams {
    logGroupName: string;
    logStreamNames?: string[];
    startTime: number;
    endTime?: number;
    filterPattern?: string;
    interleaved?: boolean;
    limit?: number;
    logStreamNamePrefix?: string;
    nextToken?: string;
}

declare interface IAWSFilterLogEventsRequestParams extends AWSCredentials, IAWSFilterLogEventsParams {

}

declare interface IAWSFilterLogEventsResponse {
    events: IAWSEvent[];
    nextToken: string;
}

declare interface IAWSQueryParams {
    queryId: string;
}

declare interface IAWSQueryRequestParams extends AWSCredentials, IAWSQueryParams {

}

declare interface IAWSQueryResultItemField {
    field: string
    value: string
}

declare type TAWSQueryResultItem = IAWSQueryResultItemField[]

declare interface IAWSQueryResponse {
    queryId?: string,
    results: TAWSQueryResultItem[],
    statistics: {
        bytesScanned?: number,
        recordsMatched?: number,
        recordsScanned?: number
    },
    status: "Running" | string,
}

declare interface IAWSStartQueryParams {
    endTime: number;
    startTime: number;
    limit?: number;
    logGroupName?: string;
    logGroupNames?: string[];
    queryString?: string,
}

declare interface IAWSStartQueryRequestParams extends AWSCredentials, IAWSStartQueryParams {

}

declare interface IAWSStartQueryResponse {
    queryId: string
}

