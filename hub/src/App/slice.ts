import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from 'store';
import { AUTH_DATA_STORAGE_KEY } from './constants';

interface AppState {
    userData: IUserSmall | null;
    authData: IUserAuthData | null;
}

const getInitialState = (): AppState => {
    let authData = null;
    const storageData = localStorage.getItem(AUTH_DATA_STORAGE_KEY);

    if (storageData) authData = JSON.parse(storageData) as IUserAuthData;

    return {
        authData,
        userData: null,
    };
};

const initialState: AppState = getInitialState();

export const appSlice = createSlice({
    name: 'app',
    initialState,

    reducers: {
        setAuthData: (state, action: PayloadAction<IUserAuthData>) => {
            state.authData = action.payload;
            localStorage.setItem(AUTH_DATA_STORAGE_KEY, JSON.stringify(action.payload));
        },
        removeAuthData: (state) => {
            state.authData = null;
            localStorage.removeItem(AUTH_DATA_STORAGE_KEY);
        },

        setUserData: (state, action: PayloadAction<IUserSmall>) => {
            state.userData = action.payload;
        },
    },
});

export const { setAuthData, removeAuthData, setUserData } = appSlice.actions;
export const selectUserData = (state: RootState) => state.app.userData;
export const selectAuthToken = (state: RootState) => state.app.authData?.token;
export const selectUserName = (state: RootState) => state.app.userData?.user_name;
export default appSlice.reducer;
