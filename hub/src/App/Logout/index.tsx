import React, { useEffect } from 'react';
import { Navigate } from 'react-router-dom';

import { useAppDispatch } from 'hooks';
import { ROUTES } from 'routes';
import { projectApi } from 'services/project';
import { userApi } from 'services/user';

import { removeAuthData } from '../slice';

export const Logout: React.FC = () => {
    const dispatch = useAppDispatch();

    useEffect(() => {
        dispatch(removeAuthData());

        dispatch(userApi.util.resetApiState());
        dispatch(projectApi.util.resetApiState());
    }, []);

    return <Navigate replace to={ROUTES.BASE} />;
};
