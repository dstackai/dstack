import { configureStore } from '@reduxjs/toolkit';
import appReducer from 'App/slice';
import { authApi } from 'services/auth';

export const store = configureStore({
    reducer: {
        app: appReducer,
        [authApi.reducerPath]: authApi.reducer,
    },

    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(authApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
