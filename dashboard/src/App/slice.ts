import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from 'store';
import auth from 'libs/auth';

interface AppState {
    currentUser: IUser | null;
    authToken: null | string;
    currentUserStatus: 'initialized' | 'loading' | 'finished' | 'error';
    progress: {
        isActive: boolean | null;
        state: number | null;
    };
}

const initialState: AppState = {
    currentUser: null,
    currentUserStatus: 'initialized',
    authToken: auth.getToken(),
    progress: {
        isActive: null,
        state: null,
    },
};

export const appSlice = createSlice({
    name: 'app',
    initialState,

    reducers: {
        setAuthToken: (state, action: PayloadAction<string>) => {
            auth.setToken(action.payload);
            state.authToken = action.payload;
        },

        clearAuthToken: (state) => {
            auth.clearToken();
            state.authToken = null;
        },

        setAppProgress: (state, action: PayloadAction<number>) => {
            state.progress.state = action.payload;
        },

        startAppProgress: (state) => {
            state.progress.isActive = true;
        },

        completeAppProgress: (state) => {
            state.progress.isActive = false;
        },

        stopAppProgress: (state) => {
            state.progress.isActive = null;
        },
    },
});

export const { setAuthToken, clearAuthToken, setAppProgress, startAppProgress, completeAppProgress, stopAppProgress } =
    appSlice.actions;
export const selectAuthToken = (state: RootState) => state.app.authToken;
export const selectAppProgress = (state: RootState) => state.app.progress;
export default appSlice.reducer;
