import auth from './auth';
import { QueryReturnValue } from '@reduxjs/toolkit/dist/query/baseQueryTypes';
import { FetchBaseQueryError, FetchBaseQueryMeta } from '@reduxjs/toolkit/dist/query/fetchBaseQuery';
import { API } from 'api';

type MockItem = {
    success: unknown;
    failed: unknown;
};

type MocksMap = {
    [key: string]: {
        [key: string]: MockItem;
    };
};

const MocksMap: MocksMap = {
    [API.AUTH.TOKEN()]: {
        POST: {
            success: auth.success,
            failed: auth.failed,
        },
    },
};

export type getResponseArgs = {
    url: string;
    method?: string;
    responseType?: keyof MockItem;
};

export type getResponseReturned = QueryReturnValue<unknown, FetchBaseQueryError, FetchBaseQueryMeta>;

export const getResponse = ({ url, method = 'GET', responseType = 'success' }: getResponseArgs): getResponseReturned => {
    if (responseType === 'failed')
        return {
            error: {
                status: 'CUSTOM_ERROR',
                error: MocksMap[url][method][responseType] as string,
            },
        };

    return { data: MocksMap[url][method][responseType] };
};
