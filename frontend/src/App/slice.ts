import type { RootState } from 'store';
import { applyMode, Mode } from '@cloudscape-design/global-styles';
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

import { AUTH_DATA_STORAGE_KEY, MODE_STORAGE_KEY } from './constants';
import { getThemeMode } from './helpers';

import { IAppState, ToolsTabs } from './types';

const getInitialState = (): IAppState => {
    let authData = null;
    let storageData = null;
    let activeMode = getThemeMode();

    try {
        storageData = localStorage.getItem(AUTH_DATA_STORAGE_KEY);
    } catch (e) {
        console.log(e);
    }

    try {
        const modeStorageData = localStorage.getItem(MODE_STORAGE_KEY);

        if (modeStorageData && JSON.parse(modeStorageData)) {
            activeMode = modeStorageData as Mode;
        }
    } catch (e) {
        console.log(e);
    }

    applyMode(activeMode);

    if (storageData) authData = JSON.parse(storageData) as IUserAuthData;

    return {
        authData,
        userData: null,
        breadcrumbs: null,
        systemMode: activeMode,

        toolsPanelState: {
            isOpen: false,
            tab: ToolsTabs.TUTORIAL,
        },

        helpPanel: {
            content: {},
        },

        tutorialPanel: {
            billingCompleted: false,
            configureCLICompleted: false,
            discordCompleted: false,
            tallyCompleted: false,
            quickStartCompleted: false,
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

        setSystemMode: (state, action: PayloadAction<Mode>) => {
            state.systemMode = action.payload;
            applyMode(action.payload);
            try {
                localStorage.setItem(MODE_STORAGE_KEY, action.payload);
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

        setUserData: (state, action: PayloadAction<IUser>) => {
            state.userData = action.payload;
        },

        setBreadcrumb: (state, action: PayloadAction<IAppState['breadcrumbs']>) => {
            state.breadcrumbs = action.payload;
        },

        openHelpPanel: (state, action: PayloadAction<IAppState['helpPanel']['content']>) => {
            state.toolsPanelState = {
                isOpen: true,
                tab: ToolsTabs.INFO,
            };

            state.helpPanel = { content: action.payload };
        },

        openTutorialPanel: (state) => {
            state.toolsPanelState = {
                isOpen: true,
                tab: ToolsTabs.TUTORIAL,
            };
        },

        closeToolsPanel: (state) => {
            state.toolsPanelState = {
                ...state.toolsPanelState,
                isOpen: false,
            };
        },

        setToolsTab: (state, action: PayloadAction<ToolsTabs>) => {
            state.toolsPanelState = {
                ...state.toolsPanelState,
                tab: action.payload,
            };
        },

        updateTutorialPanelState: (state, action: PayloadAction<Partial<IAppState['tutorialPanel']>>) => {
            state.tutorialPanel = {
                ...state.tutorialPanel,
                ...action.payload,
            };
        },
    },
});

export const {
    setAuthData,
    setSystemMode,
    removeAuthData,
    setUserData,
    setBreadcrumb,
    openHelpPanel,
    closeToolsPanel,
    setToolsTab,
    openTutorialPanel,
    updateTutorialPanelState,
} = appSlice.actions;
export const selectUserData = (state: RootState) => state.app.userData;
export const selectAuthToken = (state: RootState) => state.app.authData?.token;
export const selectUserName = (state: RootState) => state.app.userData?.username;
export const selectBreadcrumbs = (state: RootState) => state.app.breadcrumbs;
export const selectToolsPanelState = (state: RootState) => state.app.toolsPanelState;
export const selectHelpPanelContent = (state: RootState) => state.app.helpPanel.content;
export const selectTutorialPanel = (state: RootState) => state.app.tutorialPanel;
export const selectSystemMode = (state: RootState) => state.app.systemMode;
export default appSlice.reducer;
