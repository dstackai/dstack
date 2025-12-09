import { configureStore } from '@reduxjs/toolkit';

import notificationsReducer from 'components/Notifications/slice';

import { artifactApi } from 'services/artifact';
import { authApi } from 'services/auth';
import { eventApi } from 'services/events';
import { fleetApi } from 'services/fleet';
import { gatewayApi } from 'services/gateway';
import { instanceApi } from 'services/instance';
import { mainApi } from 'services/mainApi';
import { projectApi } from 'services/project';
import { repoApi } from 'services/repo';
import { runApi } from 'services/run';
import { secretApi } from 'services/secrets';
import { serverApi } from 'services/server';
import { userApi } from 'services/user';
import { volumeApi } from 'services/volume';

import appReducer from 'App/slice';

import { gpuApi } from './services/gpu';

export const store = configureStore({
    reducer: {
        app: appReducer,
        notifications: notificationsReducer,
        [projectApi.reducerPath]: projectApi.reducer,
        [runApi.reducerPath]: runApi.reducer,
        [artifactApi.reducerPath]: artifactApi.reducer,
        [fleetApi.reducerPath]: fleetApi.reducer,
        [instanceApi.reducerPath]: instanceApi.reducer,
        [userApi.reducerPath]: userApi.reducer,
        [gatewayApi.reducerPath]: gatewayApi.reducer,
        [authApi.reducerPath]: authApi.reducer,
        [serverApi.reducerPath]: serverApi.reducer,
        [volumeApi.reducerPath]: volumeApi.reducer,
        [secretApi.reducerPath]: secretApi.reducer,
        [gpuApi.reducerPath]: gpuApi.reducer,
        [repoApi.reducerPath]: repoApi.reducer,
        [mainApi.reducerPath]: mainApi.reducer,
        [eventApi.reducerPath]: eventApi.reducer,
    },

    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({
            serializableCheck: false,
        })
            .concat(projectApi.middleware)
            .concat(runApi.middleware)
            .concat(artifactApi.middleware)
            .concat(fleetApi.middleware)
            .concat(instanceApi.middleware)
            .concat(gatewayApi.middleware)
            .concat(userApi.middleware)
            .concat(authApi.middleware)
            .concat(serverApi.middleware)
            .concat(volumeApi.middleware)
            .concat(secretApi.middleware)
            .concat(gpuApi.middleware)
            .concat(eventApi.middleware)
            .concat(repoApi.middleware)
            .concat(mainApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
