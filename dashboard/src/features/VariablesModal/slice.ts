import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from 'store';

interface VariablesModalState {
    isShow: boolean;
    variables: null | IVariable[];
}

const initialState: VariablesModalState = {
    isShow: false,
    variables: null,
};

export const variablesModalSlice = createSlice({
    name: 'notifications',
    initialState,

    reducers: {
        showVariablesModal: (state, action: PayloadAction<IVariable[]>) => {
            state.variables = action.payload;
            state.isShow = true;
        },
        hideVariablesModal: (state) => {
            state.isShow = false;
            state.variables = null;
        },
    },
});

export const { showVariablesModal, hideVariablesModal } = variablesModalSlice.actions;
export const selectVariables = (state: RootState) => state.variablesModal.variables;
export const selectShowModal = (state: RootState) => state.variablesModal.isShow;
export default variablesModalSlice.reducer;
