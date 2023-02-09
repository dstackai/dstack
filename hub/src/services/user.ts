import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from 'libs/fetchBaseQuery';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';
import { API } from 'api';

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

        updateUser: builder.mutation<IUser, Partial<IUser> & Pick<IUser, 'user_name'>>({
            query: (user) => ({
                url: API.USERS.DETAILS(user.user_name),
                method: 'PATCH',
                params: user,
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
                params: {
                    users: userNames,
                },
            }),
        }),
    }),
});

export const {
    useGetUserDataQuery,
    useGetUserListQuery,
    useGetUserQuery,
    useDeleteUsersMutation,
    useUpdateUserMutation,
    useRefreshTokenMutation,
} = userApi;
