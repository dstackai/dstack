import { BaseQueryApi } from '@reduxjs/toolkit/dist/query/baseQueryTypes';

import { RootState } from '../store';

function baseQueryHeaders(headers: Headers, { getState }: Pick<BaseQueryApi, 'getState'>): Headers {
    const token = (getState() as RootState).app.authData?.token;
    const authorizationHeader = headers.get('Authorization');

    if (token && !authorizationHeader) {
        headers.set('Authorization', `Bearer ${token}`);
    }

    headers.set('X-API-VERSION', 'latest');

    return headers;
}

export function unauthorizedQueryHeaders(headers: Headers, { getState }: Pick<BaseQueryApi, 'getState'>): Headers {
    headers.set('X-API-VERSION', 'latest');
    return headers;
}

export default baseQueryHeaders;
