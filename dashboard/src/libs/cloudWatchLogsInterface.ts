import { CloudWatchLogs } from '@aws-sdk/client-cloudwatch-logs';

class CloudWatchLogsInterface {
    private instances: { [key: string]: CloudWatchLogs } = {};

    getInstance({ region, accessKeyId, secretAccessKey }: AWSCredentials): CloudWatchLogs {
        if (this.instances[`${region}|${accessKeyId}|${secretAccessKey}`])
            return this.instances[`${region}|${accessKeyId}|${secretAccessKey}`];

        const newInstance = new CloudWatchLogs({
            region,
            credentials: {
                accessKeyId,
                secretAccessKey,
            },
        });

        this.instances[`${region}|${accessKeyId}|${secretAccessKey}`] = newInstance;

        return newInstance;
    }

    async filterLogEvents(params: IAWSFilterLogEventsRequestParams): Promise<IAWSFilterLogEventsResponse> {
        const { region, accessKeyId, secretAccessKey, ...body } = params;
        const cwl = this.getInstance({ region, accessKeyId, secretAccessKey });

        return new Promise((resolve, reject) => {
            cwl.filterLogEvents(body, (err, data) => {
                if (err) {
                    reject(err);
                } else {
                    resolve(data as IAWSFilterLogEventsResponse);
                }
            });
        });
    }

    async startQuery(params: IAWSStartQueryRequestParams): Promise<IAWSStartQueryResponse> {
        const { region, accessKeyId, secretAccessKey, ...body } = params;
        const cwl = this.getInstance({ region, accessKeyId, secretAccessKey });

        return new Promise((resolve, reject) => {
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-ignore
            cwl.startQuery(body, (err, data) => {
                if (err) {
                    reject(err);
                } else {
                    resolve(data as IAWSStartQueryResponse);
                }
            });
        });
    }

    async query(params: IAWSQueryRequestParams): Promise<IAWSQueryResponse> {
        const { region, accessKeyId, secretAccessKey } = params;
        const cwl = this.getInstance({ region, accessKeyId, secretAccessKey });

        return new Promise((resolve, reject) => {
            cwl.getQueryResults(params, (err, data) => {
                if (err) {
                    reject(err);
                } else {
                    const result = {
                        ...data,
                    } as IAWSQueryResponse;

                    resolve(result);
                }
            });
        });
    }
}

export default new CloudWatchLogsInterface();
