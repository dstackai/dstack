import { API } from 'api';
import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const userApi = createApi({
    reducerPath: 'userApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['User'],

    endpoints: (builder) => ({
        getUserData: builder.query<IUserSmall, void>({
            query: () => {
                return {
                    url: API.USERS.INFO(),
                };
            },
        }),

        getUserList: builder.query<IUser[], void>({
            query: () => {
                return {
                    url: API.USERS.LIST(),
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ user_name }) => ({ type: 'User' as const, id: user_name })), 'User'] : ['User'],
        }),

        getUser: builder.query<IUser, { name: IUser['user_name'] }>({
            query: (arg) => {
                return {
                    url: API.USERS.DETAILS(arg.name),
                };
            },

            providesTags: (result) => (result ? [{ type: 'User' as const, id: result.user_name }] : []),
        }),

        createUser: builder.mutation<IUser, Omit<IUser, 'token'>>({
            query: (user) => ({
                url: API.USERS.BASE(),
                method: 'POST',
                body: user,
            }),

            invalidatesTags: (result) => [{ type: 'User' as const, id: result?.user_name }, 'User'],
        }),

        updateUser: builder.mutation<IUser, Partial<IUser> & Pick<IUser, 'user_name'>>({
            query: (user) => ({
                url: API.USERS.DETAILS(user.user_name),
                method: 'PATCH',
                body: user,
            }),

            invalidatesTags: (result) => [{ type: 'User' as const, id: result?.user_name }],
        }),

        refreshToken: builder.mutation<Pick<IUser, 'token'>, Pick<IUser, 'user_name'>>({
            query: ({ user_name }) => ({
                url: API.USERS.REFRESH_TOKEN(user_name),
                method: 'POST',
            }),

            invalidatesTags: (result, error, { user_name }) => [{ type: 'User' as const, id: user_name }],
        }),

        deleteUsers: builder.mutation<void, IUser['user_name'][]>({
            query: (userNames) => ({
                url: API.USERS.BASE(),
                method: 'DELETE',
                body: {
                    users: userNames,
                },
            }),

            invalidatesTags: ['User'],
        }),
    }),
});

export const {
    useGetUserDataQuery,
    useGetUserListQuery,
    useGetUserQuery,
    useCreateUserMutation,
    useDeleteUsersMutation,
    useUpdateUserMutation,
    useRefreshTokenMutation,
} = userApi;
