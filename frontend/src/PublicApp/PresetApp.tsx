import React, { createContext, useContext, useState } from 'react';

import { useAppSelector } from 'hooks';
import { useGetUserDataQuery } from 'services/user';

import App from 'App';
import { Loading } from 'App/Loading';
import { selectAuthToken } from 'App/slice';

import { PublicApp } from './index';

const PresetViewer = createContext<{
    isAuthenticated: boolean;
    scope: 'mine' | 'public';
    setScope: (scope: 'mine' | 'public') => void;
}>({ isAuthenticated: false, scope: 'public', setScope: () => undefined });

export const usePresetViewer = () => useContext(PresetViewer);

export const PresetApp: React.FC = () => {
    const token = useAppSelector(selectAuthToken);
    const [scope, setScope] = useState<'mine' | 'public'>('mine');
    const { currentData, error, isFetching } = useGetUserDataQuery({ token }, { skip: !token || !('localStorage' in window) });
    const isAuthenticated = Boolean(token && currentData?.username && !error);

    if (token && isFetching && !currentData) return <Loading />;

    return (
        <PresetViewer.Provider value={{ isAuthenticated, scope: isAuthenticated ? scope : 'public', setScope }}>
            {isAuthenticated ? <App /> : <PublicApp />}
        </PresetViewer.Provider>
    );
};
