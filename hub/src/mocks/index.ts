import { QueryReturnValue } from '@reduxjs/toolkit/dist/query/baseQueryTypes';
import { FetchBaseQueryError, FetchBaseQueryMeta } from '@reduxjs/toolkit/dist/query/fetchBaseQuery';
import { matchPath } from 'react-router';
import { API } from 'api';

import user from './user';
import hub from './hub';

type MockItem = {
    success: unknown;
    failed: unknown;
};

type MocksMap = {
    [key: string]: {
        [key: string]: MockItem;
    };
};

const mocksMap: MocksMap = {
    [API.USERS.INFO()]: {
        GET: {
            success: user.info.success,
            failed: user.info.failed,
        },
    },
    [API.USERS.LIST()]: {
        GET: {
            success: user.list.success,
            failed: { status: 403 },
        },
    },
    [API.USERS.DETAILS(':name')]: {
        GET: {
            success: user.list.success[0],
            failed: { status: 403 },
        },
        PATCH: {
            success: user.list.success[0],
            failed: { status: 403 },
        },
    },
    [API.USERS.REFRESH_TOKEN(':name')]: {
        POST: {
            success: { token: user.list.success[0].token },
            failed: { status: 403 },
        },
    },
    [API.USERS.BASE()]: {
        DELETE: {
            success: {},
            failed: { status: 403 },
        },
        POST: {
            success: user.list.success[0],
            failed: { status: 403 },
        },
    },

    // hubs
    [API.HUBS.LIST()]: {
        GET: {
            success: hub.list.success,
            failed: { status: 403 },
        },
    },
    [API.HUBS.DETAILS(':name')]: {
        GET: {
            success: hub.list.success[0],
            failed: { status: 403 },
        },
        PATCH: {
            success: hub.list.success[0],
            failed: { status: 403 },
        },
    },
    [API.HUBS.MEMBERS(':name')]: {
        POST: {
            success: hub.list.success[0].members,
            failed: { status: 403 },
        },
    },
    [API.HUBS.BASE()]: {
        DELETE: {
            success: {},
            failed: { status: 403 },
        },
        POST: {
            success: hub.list.success[0],
            failed: { status: 403 },
        },
    },
    [API.HUBS.BACKEND_VALUES()]: {
        POST: {
            success: hub.backendValues.success,
            failed: { status: 400 },
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
    const formattedUrl = url.replace(/\?.+/gi, '');
    const matchUrl = Object.keys(mocksMap).find((path) => !!matchPath(path, formattedUrl));

    if (matchUrl) {
        if (responseType === 'failed')
            return {
                error: mocksMap[matchUrl][method][responseType] as FetchBaseQueryError,
            };

        return { data: mocksMap[matchUrl][method][responseType] };
    }

    return {
        error: { status: 404 } as FetchBaseQueryError,
    };
};
