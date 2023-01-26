import { configureStore } from '@reduxjs/toolkit';
import appReducer from 'App/slice';
import { authApi } from 'services/auth';
import { hubApi } from 'services/hub';

export const store = configureStore({
    reducer: {
        app: appReducer,
        [authApi.reducerPath]: authApi.reducer,
        [hubApi.reducerPath]: hubApi.reducer,
    },

    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(hubApi.middleware).concat(authApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
