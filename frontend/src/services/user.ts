import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

import { UserPermission, userPermissionMap } from '../types';

export const userApi = createApi({
    reducerPath: 'userApi',
    refetchOnMountOrArgChange: true,
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['User', 'Payments', 'Billing'],

    endpoints: (builder) => ({
        getUserData: builder.query<IUser, Partial<IUserAuthData>>({
            query: () => {
                return {
                    url: API.USERS.CURRENT_USER(),
                    method: 'POST',
                };
            },

            transformResponse: (userData: IUserResponseData): IUser => {
                return {
                    ...userData,
                    permissions: Object.keys(userPermissionMap).reduce<TUserPermission[]>((acc, key) => {
                        if (userData?.permissions?.[key as TUserPermissionKeys]) {
                            acc.push(UserPermission[userPermissionMap[key as TUserPermissionKeys]]);
                        }

                        return acc;
                    }, []),
                };
            },
        }),

        getUserList: builder.query<IUser[], void>({
            query: () => {
                return {
                    url: API.USERS.LIST(),
                    method: 'POST',
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ username }) => ({ type: 'User' as const, id: username })), 'User'] : ['User'],
        }),

        getUser: builder.query<IUserWithCreds, { name: IUser['username'] }>({
            query: ({ name }) => {
                return {
                    url: API.USERS.DETAILS(),
                    method: 'POST',
                    body: {
                        username: name,
                    },
                };
            },

            providesTags: (result) => (result ? [{ type: 'User' as const, id: result.username }] : []),
        }),

        checkAuthToken: builder.mutation<IUser, { token: string }>({
            query: ({ token }) => ({
                url: API.USERS.CURRENT_USER(),
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            }),
        }),

        createUser: builder.mutation<IUser, Omit<IUser, 'id'>>({
            query: (user) => ({
                url: API.USERS.CREATE(),
                method: 'POST',
                body: user,
            }),

            invalidatesTags: (result) => [{ type: 'User' as const, id: result?.username }, 'User'],
        }),

        updateUser: builder.mutation<IUser, Partial<IUser> & Pick<IUser, 'username'>>({
            query: (user) => ({
                url: API.USERS.UPDATE(),
                method: 'POST',
                body: user,
            }),

            invalidatesTags: (result) => [{ type: 'User' as const, id: result?.username }],
        }),

        refreshToken: builder.mutation<IUserWithCreds, Pick<IUser, 'username'>>({
            query: ({ username }) => ({
                url: API.USERS.REFRESH_TOKEN(),
                method: 'POST',
                body: { username },
            }),

            // invalidatesTags: (result, error, { username }) => [{ type: 'User' as const, id: username }],

            async onQueryStarted({ username }, { dispatch, queryFulfilled }) {
                try {
                    const { data } = await queryFulfilled;

                    dispatch(
                        userApi.util.updateQueryData('getUser', { name: username }, (draft) => {
                            Object.assign(draft, data);
                        }),
                    );
                } catch (e) {
                    console.log(e);
                }
            },
        }),

        deleteUsers: builder.mutation<void, IUser['username'][]>({
            query: (userNames) => ({
                url: API.USERS.DELETE(),
                method: 'POST',
                body: {
                    users: userNames,
                },
            }),

            invalidatesTags: ['User'],
        }),

        getUserPayments: builder.query<IPayment[], { username: IUser['username'] }>({
            query: ({ username }) => {
                return {
                    url: API.USER_PAYMENTS.LIST(username),
                    method: 'POST',
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ id }) => ({ type: 'Payments' as const, id })), 'Payments'] : ['Payments'],
        }),

        addUserPayment: builder.mutation<IPayment, Pick<IPayment, 'description' | 'value'> & { username: IUser['username'] }>({
            query: ({ username, ...body }) => ({
                url: API.USER_PAYMENTS.ADD(username),
                method: 'POST',
                body,
            }),

            invalidatesTags: ['Payments'],
        }),

        getUserBillingInfo: builder.query<IUserBillingInfo, { username: string }>({
            query: ({ username }) => {
                return {
                    url: API.USER_BILLING.INFO(username),
                    method: 'POST',
                };
            },

            transformResponse: (response: IUserBillingInfo) => ({
                ...response,
            }),

            providesTags: ['Billing'],
        }),

        userBillingCheckoutSession: builder.mutation<{ url: string }, { username: string; amount: number }>({
            query: ({ username, ...body }) => {
                return {
                    url: API.USER_BILLING.CHECKOUT_SESSION(username),
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: ['Billing'],
        }),

        userBillingPortalSession: builder.mutation<{ url: string }, { username: string }>({
            query: ({ username }) => {
                return {
                    url: API.USER_BILLING.PORTAL_SESSION(username),
                    method: 'POST',
                };
            },

            invalidatesTags: ['Billing'],
        }),
    }),
});

export const {
    useGetUserDataQuery,
    useGetUserListQuery,
    useGetUserQuery,
    useCheckAuthTokenMutation,
    useCreateUserMutation,
    useDeleteUsersMutation,
    useUpdateUserMutation,
    useRefreshTokenMutation,
    useGetUserPaymentsQuery,
    useAddUserPaymentMutation,
    useGetUserBillingInfoQuery,
    useUserBillingCheckoutSessionMutation,
    useUserBillingPortalSessionMutation,
} = userApi;
