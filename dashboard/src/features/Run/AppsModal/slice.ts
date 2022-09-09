import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from 'store';

interface AppsModalState {
    openModal: boolean;
    items: IApp[] | null;
}

const initialState: AppsModalState = {
    openModal: false,
    items: null,
};

export const appsModalSlice = createSlice({
    name: 'notifications',
    initialState,

    reducers: {
        showAppsModal: (state, action: PayloadAction<IApp[]>) => {
            state.items = action.payload;
            state.openModal = true;
        },

        closeModal: (state) => {
            state.openModal = false;
            state.items = null;
        },
    },
});

export const { showAppsModal, closeModal } = appsModalSlice.actions;
export const selectApps = (state: RootState) => state.appsModal.items;
export const selectOpenModal = (state: RootState) => state.appsModal.openModal;
export default appsModalSlice.reducer;
