import { configureStore } from '@reduxjs/toolkit';

import notificationsReducer from 'components/Notifications/slice';

import { artifactApi } from 'services/artifact';
import { projectApi } from 'services/project';
import { runApi } from 'services/run';
import { tagApi } from 'services/tag';
import { userApi } from 'services/user';

import appReducer from 'App/slice';

export const store = configureStore({
    reducer: {
        app: appReducer,
        notifications: notificationsReducer,
        [projectApi.reducerPath]: projectApi.reducer,
        [runApi.reducerPath]: runApi.reducer,
        [artifactApi.reducerPath]: artifactApi.reducer,
        [tagApi.reducerPath]: tagApi.reducer,
        [userApi.reducerPath]: userApi.reducer,
    },

    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({
            serializableCheck: false,
        })
            .concat(projectApi.middleware)
            .concat(runApi.middleware)
            .concat(artifactApi.middleware)
            .concat(tagApi.middleware)
            .concat(userApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
