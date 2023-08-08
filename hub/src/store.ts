import { configureStore } from '@reduxjs/toolkit';

import notificationsReducer from 'components/Notifications/slice';

import { artifactApi } from 'services/artifact';
import { backendApi } from 'services/backend';
import { projectApi } from 'services/project';
import { runApi } from 'services/run';
import { secretApi } from 'services/secret';
import { tagApi } from 'services/tag';
import { userApi } from 'services/user';

import appReducer from 'App/slice';

export const store = configureStore({
    reducer: {
        app: appReducer,
        notifications: notificationsReducer,
        [projectApi.reducerPath]: projectApi.reducer,
        [backendApi.reducerPath]: backendApi.reducer,
        [runApi.reducerPath]: runApi.reducer,
        [artifactApi.reducerPath]: artifactApi.reducer,
        [tagApi.reducerPath]: tagApi.reducer,
        [userApi.reducerPath]: userApi.reducer,
        [secretApi.reducerPath]: secretApi.reducer,
    },

    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({
            serializableCheck: false,
        })
            .concat(projectApi.middleware)
            .concat(backendApi.middleware)
            .concat(runApi.middleware)
            .concat(artifactApi.middleware)
            .concat(tagApi.middleware)
            .concat(secretApi.middleware)
            .concat(userApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
