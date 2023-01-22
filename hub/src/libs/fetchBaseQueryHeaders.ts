import { BaseQueryApi } from '@reduxjs/toolkit/dist/query/baseQueryTypes';
import { RootState } from '../store';

function baseQueryHeaders(headers: Headers, { getState }: Pick<BaseQueryApi, 'getState'>): Headers {
    const token = (getState() as RootState).app.authData?.token;

    if (token) {
        headers.set('Authorization', `Bearer ${token}`);
    }

    return headers;
}

export default baseQueryHeaders;
