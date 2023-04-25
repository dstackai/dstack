import type { RootState } from 'store';
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

import { Notification } from './types';

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
        push: (state, action: PayloadAction<Notification>) => {
            state.items = [...state.items, action.payload];
        },
        remove: (state, action: PayloadAction<Notification['id']>) => {
            state.items = state.items.filter((i) => i.id !== action.payload);
        },
    },
});

export const { remove, push } = notificationsSlice.actions;
export const selectNotifications = (state: RootState) => state.notifications.items;
export default notificationsSlice.reducer;
