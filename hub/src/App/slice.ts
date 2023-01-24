import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from 'store';
import { AUTH_DATA_STORAGE_KEY } from './constants';

interface AppState {
    authData: IUserSmall | null;
}

const getInitialState = (): AppState => {
    let authData = null;
    const storageData = localStorage.getItem(AUTH_DATA_STORAGE_KEY);

    if (storageData) authData = JSON.parse(storageData) as IUserSmall;

    return {
        authData,
    };
};

const initialState: AppState = getInitialState();

export const appSlice = createSlice({
    name: 'app',
    initialState,

    reducers: {
        setAuthData: (state, action: PayloadAction<IUserSmall>) => {
            state.authData = action.payload;
            localStorage.setItem(AUTH_DATA_STORAGE_KEY, JSON.stringify(action.payload));
        },
        removeAuthData: (state) => {
            state.authData = null;
            localStorage.removeItem(AUTH_DATA_STORAGE_KEY);
        },
    },
});

export const { setAuthData, removeAuthData } = appSlice.actions;
export const selectAuthData = (state: RootState) => state.app.authData;
export const selectIsAuthenticated = (state: RootState) => !!state.app.authData?.token;
export const selectUserName = (state: RootState) => state.app.authData?.user_name;
export default appSlice.reducer;
