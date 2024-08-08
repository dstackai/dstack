import { fetchBaseQuery } from '@reduxjs/toolkit/dist/query/react';
import { createApi } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from '../libs/fetchBaseQueryHeaders';

export const mainApi = createApi({
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),
    endpoints: () => ({}),
});
