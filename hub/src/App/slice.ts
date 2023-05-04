import type { RootState } from 'store';
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

import { AUTH_DATA_STORAGE_KEY } from './constants';

import { IAppState } from './types';

const getInitialState = (): IAppState => {
    let authData = null;
    let storageData = null;

    try {
        storageData = localStorage.getItem(AUTH_DATA_STORAGE_KEY);
    } catch (e) {
        console.log(e);
    }

    if (storageData) authData = JSON.parse(storageData) as IUserAuthData;

    return {
        authData,
        userData: null,
        breadcrumbs: null,

        helpPanel: {
            open: false,
            content: {},
        },
    };
};

const initialState: IAppState = getInitialState();

export const appSlice = createSlice({
    name: 'app',
    initialState,

    reducers: {
        setAuthData: (state, action: PayloadAction<IUserAuthData>) => {
            state.authData = action.payload;

            try {
                localStorage.setItem(AUTH_DATA_STORAGE_KEY, JSON.stringify(action.payload));
            } catch (e) {
                console.log(e);
            }
        },
        removeAuthData: (state) => {
            state.authData = null;

            try {
                localStorage.removeItem(AUTH_DATA_STORAGE_KEY);
            } catch (e) {
                console.log(e);
            }
        },

        setUserData: (state, action: PayloadAction<IUserSmall>) => {
            state.userData = action.payload;
        },

        setBreadcrumb: (state, action: PayloadAction<IAppState['breadcrumbs']>) => {
            state.breadcrumbs = action.payload;
        },

        openHelpPanel: (state, action: PayloadAction<IAppState['helpPanel']['content']>) => {
            state.helpPanel = {
                open: true,
                content: action.payload,
            };
        },

        closeHelpPanel: (state) => {
            state.helpPanel = {
                open: false,
                content: {},
            };
        },
    },
});

export const { setAuthData, removeAuthData, setUserData, setBreadcrumb, openHelpPanel, closeHelpPanel } = appSlice.actions;
export const selectUserData = (state: RootState) => state.app.userData;
export const selectAuthToken = (state: RootState) => state.app.authData?.token;
export const selectUserName = (state: RootState) => state.app.userData?.user_name;
export const selectBreadcrumbs = (state: RootState) => state.app.breadcrumbs;
export const selectHelpPanelOpen = (state: RootState) => state.app.helpPanel.open;
export const selectHelpPanelContent = (state: RootState) => state.app.helpPanel.content;
export default appSlice.reducer;
