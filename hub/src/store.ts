import { configureStore } from '@reduxjs/toolkit';

import notificationsReducer from 'components/Notifications/slice';

import { projectApi } from 'services/project';
import { userApi } from 'services/user';

import appReducer from 'App/slice';

export const store = configureStore({
    reducer: {
        app: appReducer,
        notifications: notificationsReducer,
        [userApi.reducerPath]: userApi.reducer,
        [projectApi.reducerPath]: projectApi.reducer,
    },

    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({
            serializableCheck: false,
        })
            .concat(projectApi.middleware)
            .concat(userApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
