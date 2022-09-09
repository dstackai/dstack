import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from 'store';
import { Notification } from './types';
import { getUid } from 'libs';

interface NotificationsState {
    items: Notification[];
}

const initialState: NotificationsState = {
    items: [],
};

export const notificationsSlice = createSlice({
    name: 'notifications',
    initialState,

    reducers: {
        addNotification: (state, action: PayloadAction<Omit<Notification, 'uid'>>) => {
            state.items.push({
                uid: getUid(),
                ...action.payload,
            });
        },

        removeNotification: (state, action: PayloadAction<Notification['uid']>) => {
            state.items = state.items.filter((n) => n.uid !== action.payload);
        },

        removeAllNotifications: (state) => {
            state.items = [];
        },
    },
});

export const { addNotification, removeNotification, removeAllNotifications } = notificationsSlice.actions;
export const selectNotifications = (state: RootState) => state.notifications.items;
export default notificationsSlice.reducer;
