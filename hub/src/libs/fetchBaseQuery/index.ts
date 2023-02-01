import { fetchBaseQuery as fetchBaseQueryRTK } from '@reduxjs/toolkit/query/react';
import {
    FetchArgs,
    FetchBaseQueryArgs,
    FetchBaseQueryError,
    FetchBaseQueryMeta,
} from '@reduxjs/toolkit/dist/query/fetchBaseQuery';
import { BaseQueryFn } from '@reduxjs/toolkit/dist/query/baseQueryTypes';
import { getResponse, getResponseArgs } from 'mocks';
import { wait } from '../';

const isMockingEnabled = process.env.ENABLE_API_MOCKING;
// const isMockingEnabled = false;

export const fetchBaseQuery = (
    params?: FetchBaseQueryArgs,
    // eslint-disable-next-line @typescript-eslint/ban-types
): BaseQueryFn<
    FetchArgs,
    unknown,
    FetchBaseQueryError,
    { responseType?: getResponseArgs['responseType'] },
    FetchBaseQueryMeta
> => {
    if (isMockingEnabled) {
        return async ({ url, method, body, params }) => {
            const response = getResponse({ url, method });
            // const response = getResponse({ url, method, responseType: 'failed' });

            console.log('Mock request', {
                url,
                method,
                response,
                body,
                params,
            });

            await wait(Math.floor(Math.random() * 3000));
            return response;
        };
    }

    return fetchBaseQueryRTK(params);
};
