import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from '../libs/fetchBaseQueryHeaders';

export const mainApi = createApi({
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),
    endpoints: () => ({}),
});
