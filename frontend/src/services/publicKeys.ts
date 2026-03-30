import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export interface IPublicKey {
    id: string;
    added_at: string;
    name: string;
    type: string;
    fingerprint: string;
}

export const publicKeysApi = createApi({
    reducerPath: 'publicKeysApi',
    refetchOnMountOrArgChange: true,
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['PublicKey'],

    endpoints: (builder) => ({
        listPublicKeys: builder.query<IPublicKey[], void>({
            query: () => ({
                url: API.USER_PUBLIC_KEYS.LIST(),
                method: 'POST',
            }),
            providesTags: (result) =>
                result ? [...result.map(({ id }) => ({ type: 'PublicKey' as const, id })), 'PublicKey'] : ['PublicKey'],
        }),

        addPublicKey: builder.mutation<IPublicKey, { key: string; name?: string }>({
            query: (body) => ({
                url: API.USER_PUBLIC_KEYS.ADD(),
                method: 'POST',
                body,
            }),
            invalidatesTags: ['PublicKey'],
        }),

        deletePublicKeys: builder.mutation<void, string[]>({
            query: (ids) => ({
                url: API.USER_PUBLIC_KEYS.DELETE(),
                method: 'POST',
                body: { ids },
            }),
            invalidatesTags: ['PublicKey'],
        }),
    }),
});

export const { useListPublicKeysQuery, useAddPublicKeyMutation, useDeletePublicKeysMutation } = publicKeysApi;
