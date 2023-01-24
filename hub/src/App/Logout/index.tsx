import React, { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { useAppDispatch } from 'hooks';
import { removeAuthData } from '../slice';
import { ROUTES } from 'routes';

export const Logout: React.FC = () => {
    const dispatch = useAppDispatch();

    useEffect(() => {
        dispatch(removeAuthData());
    }, []);

    return <Navigate replace to={ROUTES.BASE} />;
};
