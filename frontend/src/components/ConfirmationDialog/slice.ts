import type { RootState } from 'store';
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

import { IProps as ConfirmationDialogProps } from './types';

type ConfirmationDialogPropsWithUuid = ConfirmationDialogProps & { uuid: string };

type ConfirmationDialogsStata = {
    dialogs: Array<ConfirmationDialogPropsWithUuid>;
};

const initialState: ConfirmationDialogsStata = {
    dialogs: [],
};

export const confirmationSlice = createSlice({
    name: 'confirmation',
    initialState,

    reducers: {
        open: (state, action: PayloadAction<ConfirmationDialogPropsWithUuid>) => {
            state.dialogs = [...state.dialogs, action.payload];
        },
        close: (state, action: PayloadAction<ConfirmationDialogPropsWithUuid['uuid']>) => {
            state.dialogs = state.dialogs.filter((i) => i.uuid !== action.payload);
        },
    },
});

export const { open, close } = confirmationSlice.actions;

export const selectConfirmationDialogs = (state: RootState) => state.confirmation.dialogs;

export default confirmationSlice.reducer;
