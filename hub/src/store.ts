import { configureStore } from '@reduxjs/toolkit';

import notificationsReducer from 'components/Notifications/slice';

import { projectApi } from 'services/project';
import { runApi } from 'services/run';
import { userApi } from 'services/user';

import appReducer from 'App/slice';

export const store = configureStore({
    reducer: {
        app: appReducer,
        notifications: notificationsReducer,
        [projectApi.reducerPath]: projectApi.reducer,
        [runApi.reducerPath]: runApi.reducer,
        [userApi.reducerPath]: userApi.reducer,
    },

    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({
            serializableCheck: false,
        })
            .concat(projectApi.middleware)
            .concat(runApi.middleware)
            .concat(userApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
