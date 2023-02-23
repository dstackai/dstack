import { configureStore } from '@reduxjs/toolkit';
import appReducer from 'App/slice';
import notificationsReducer from 'components/Notifications/slice';
import { userApi } from 'services/user';
import { hubApi } from 'services/hub';

export const store = configureStore({
    reducer: {
        app: appReducer,
        notifications: notificationsReducer,
        [userApi.reducerPath]: userApi.reducer,
        [hubApi.reducerPath]: hubApi.reducer,
    },

    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({
            serializableCheck: false,
        })
            .concat(hubApi.middleware)
            .concat(userApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
