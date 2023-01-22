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

const isTest = true;

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
    if (isTest) {
        return async ({ url, method, body, params }) => {
            await wait(Math.floor(Math.random() * 3000));

            return getResponse({ url, method });
            // return getResponse({ url, method, responseType: 'failed' });
        };
    }

    return fetchBaseQueryRTK(params);
};
