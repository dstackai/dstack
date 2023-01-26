import { QueryReturnValue } from '@reduxjs/toolkit/dist/query/baseQueryTypes';
import { FetchBaseQueryError, FetchBaseQueryMeta } from '@reduxjs/toolkit/dist/query/fetchBaseQuery';
import { API } from 'api';

import auth from './auth';
import hub from './hub';

type MockItem = {
    success: unknown;
    failed: unknown;
};

type RequestMethod = 'GET' | 'POST';

type MocksMap = {
    [key: string]: {
        [key: string]: MockItem;
    };
};

const mocksMap: MocksMap = {
    [API.AUTH.TOKEN()]: {
        POST: {
            success: auth.success,
            failed: auth.failed,
        },
    },
    [API.HUB.LIST()]: {
        GET: {
            success: hub.list.success,
            failed: {},
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
                error: 'Forbidden',
                data: mocksMap[url][method][responseType] as string,
            },
        };

    return { data: mocksMap[url][method][responseType] };
};
