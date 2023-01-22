import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { useCheckTokenMutation } from 'services/auth';
import { isValidToken } from 'libs';
import { useAppDispatch, useAppSelector } from 'hooks';
import AppLayout from 'layouts/AppLayout';
import { selectIsAuthenticated, setAuthData } from './slice';

const App: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const token = searchParams.get('token');
    const isAuthenticated = useAppSelector(selectIsAuthenticated);
    const [isAuthorizing, setIsAuthorizing] = useState(isValidToken(token));
    const dispatch = useAppDispatch();

    const [checkToken, { isLoading, data: checkingData, error: checkingError }] = useCheckTokenMutation();

    useEffect(() => {
        if (isValidToken(token)) {
            checkToken({ token: token! });
            setSearchParams();
        }
    }, []);

    useEffect(() => {
        if (checkingData?.token || checkingError) {
            setIsAuthorizing(false);

            if (checkingData?.token) dispatch(setAuthData(checkingData));
        }
    }, [checkingData, checkingError, isLoading]);

    const renderTokenError = () => {
        const errorKey = 'error' in checkingError! ? checkingError.error : '';

        if (errorKey) return <div>{t(`auth.${errorKey}`)}</div>;

        return <div>{t('auth.token_error')}</div>;
    };

    if (isAuthorizing) return <div>Loading</div>;

    if (checkingError) return renderTokenError();

    if (!isAuthenticated && !token) return <div>Unauthorized</div>;

    return <AppLayout>Hello word</AppLayout>;
};

export default App;
