import { configureStore } from '@reduxjs/toolkit';

import notificationsReducer from 'components/Notifications/slice';

import { artifactApi } from 'services/artifact';
import { authApi } from 'services/auth';
import { fleetApi } from 'services/fleet';
import { gatewayApi } from 'services/gateway';
import { mainApi } from 'services/mainApi';
import { poolApi } from 'services/pool';
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
        [artifactApi.reducerPath]: artifactApi.reducer,
        [poolApi.reducerPath]: poolApi.reducer,
        [fleetApi.reducerPath]: fleetApi.reducer,
        [userApi.reducerPath]: userApi.reducer,
        [gatewayApi.reducerPath]: gatewayApi.reducer,
        [authApi.reducerPath]: authApi.reducer,
        [authApi.mainApi]: mainApi.reducer,
    },

    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({
            serializableCheck: false,
        })
            .concat(projectApi.middleware)
            .concat(runApi.middleware)
            .concat(artifactApi.middleware)
            .concat(fleetApi.middleware)
            .concat(poolApi.middleware)
            .concat(gatewayApi.middleware)
            .concat(userApi.middleware)
            .concat(authApi.middleware)
            .concat(mainApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
