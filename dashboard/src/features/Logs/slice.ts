import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from 'store';

interface LogsState {
    hasLogs: {
        [key: string]: boolean;
    };
}

const initialState: LogsState = {
    hasLogs: {},
};

export const logsSlice = createSlice({
    name: 'logs',
    initialState,

    reducers: {
        setHasLogs: (state, action: PayloadAction<{ fullName: string; has: boolean }>) => {
            state.hasLogs = {
                ...state.hasLogs,
                [action.payload.fullName]: action.payload.has,
            };
        },

        resetHasLogs: (state, action: PayloadAction<string>) => {
            delete state.hasLogs[action.payload];
        },
    },
});

export const { setHasLogs, resetHasLogs } = logsSlice.actions;
export const selectHasLogs = (state: RootState) => state.logs.hasLogs;
export default logsSlice.reducer;
