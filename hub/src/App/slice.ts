import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from 'store';

interface AppState {
    authData: IUserSmall | null;
}

const getInitialState = (): AppState => {
    let authData = null;
    const storageData = localStorage.getItem('authData');

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
            localStorage.setItem('authData', JSON.stringify(action.payload));
        },
    },
});

export const { setAuthData } = appSlice.actions;
export const selectAuthData = (state: RootState) => state.app.authData;
export const selectIsAuthenticated = (state: RootState) => !!state.app.authData?.token;
export default appSlice.reducer;
