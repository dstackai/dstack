import { configureStore } from '@reduxjs/toolkit';
import appReducer from 'App/slice';
import notificationsReducer from 'features/Notifications/slice';
import variablesModalReducer from 'features/VariablesModal/slice';
import appsModalReducer from 'features/Run/AppsModal/slice';
import logsReducer from 'features/Logs/slice';
import artifactsModalReducer from 'features/ArtifactsModal/slice';
import { runApi } from 'services/runs';
import { jobApi } from 'services/jobs';
import { runnerApi } from 'services/runners';
import { userApi } from 'services/user';
import { onDemandApi } from 'services/onDemand';
import { awsLogsApi } from 'services/awsLogs';
import { secretApi } from 'services/secrets';
import { artifactsApi } from 'services/artifacts';
import { workflowApi } from 'services/workflows';
import { repositoryApi } from 'services/repositories';
import { tagsApi } from 'services/tags';

export const store = configureStore({
    reducer: {
        app: appReducer,
        notifications: notificationsReducer,
        variablesModal: variablesModalReducer,
        appsModal: appsModalReducer,
        logs: logsReducer,
        artifactsModal: artifactsModalReducer,
        [runApi.reducerPath]: runApi.reducer,
        [jobApi.reducerPath]: jobApi.reducer,
        [runnerApi.reducerPath]: runnerApi.reducer,
        [userApi.reducerPath]: userApi.reducer,
        [onDemandApi.reducerPath]: onDemandApi.reducer,
        [awsLogsApi.reducerPath]: awsLogsApi.reducer,
        [secretApi.reducerPath]: secretApi.reducer,
        [artifactsApi.reducerPath]: artifactsApi.reducer,
        [workflowApi.reducerPath]: workflowApi.reducer,
        [repositoryApi.reducerPath]: repositoryApi.reducer,
        [tagsApi.reducerPath]: tagsApi.reducer,
    },

    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware()
            .concat(runApi.middleware)
            .concat(jobApi.middleware)
            .concat(runnerApi.middleware)
            .concat(userApi.middleware)
            .concat(onDemandApi.middleware)
            .concat(awsLogsApi.middleware)
            .concat(secretApi.middleware)
            .concat(artifactsApi.middleware)
            .concat(workflowApi.middleware)
            .concat(repositoryApi.middleware)
            .concat(tagsApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
