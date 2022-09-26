import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from 'store';

interface ArtifactsModal {
    artifacts: TArtifacts | null;
    params: Omit<IArtifactsFetchParams, 'path' | 'job_id'> | null;
}

const initialState: ArtifactsModal = {
    artifacts: null,
    params: null,
};

export const artifactsModalSlice = createSlice({
    name: 'artifactsModal',
    initialState,

    reducers: {
        showArtifacts: (state, action: PayloadAction<ArtifactsModal['params'] & { artifacts: TArtifacts }>) => {
            const { artifacts, ...params } = action.payload;
            state.artifacts = artifacts;
            state.params = params;
        },

        closeArtifacts: (state) => {
            state.artifacts = null;
            state.params = null;
        },
    },
});

export const { showArtifacts, closeArtifacts } = artifactsModalSlice.actions;
export const selectArtifacts = (state: RootState) => state.artifactsModal.artifacts;
export const selectParams = (state: RootState) => state.artifactsModal.params;
export default artifactsModalSlice.reducer;
