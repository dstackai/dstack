import React, { useEffect } from 'react';
import { useNavigate, useLocation, useRoutes } from 'react-router-dom';
import TableContentSkeleton from 'components/TableContentSkeleton';
import AuthLayout from 'layouts/AuthLayout';

import { useAppSelector, useAppDispatch, useNotifications } from 'hooks';
import { clearAuthToken, selectAuthToken } from './slice';
import { useGetUserInfoQuery } from 'services/user';
import { getUrlWithOutTrailingSlash } from 'libs';
import { useTranslation } from 'react-i18next';
import { newRouter } from 'route/ApplicationRouter';
import { URL_PARAMS } from 'route/url-params';

const noAppRoutes = new Set([
    newRouter.buildUrl('app'),
    newRouter.buildUrl('auth.login'),
    newRouter.buildUrl('auth.signup-email'),
    newRouter.buildUrl('auth.create-session'),
]);

const isHost = process.env.HOST;

const App: React.FC = () => {
    const { t } = useTranslation();
    const location = useLocation();
    const navigate = useNavigate();
    const authToken = useAppSelector(selectAuthToken);
    const dispatch = useAppDispatch();
    const { push: pushNotification } = useNotifications();

    const element = useRoutes(newRouter.getReactRouterRoutes());

    const { data, isLoading, isSuccess, isError, error } = useGetUserInfoQuery(undefined, {
        skip:
            isHost || !authToken || getUrlWithOutTrailingSlash(location.pathname) === newRouter.buildUrl('auth.create-session'),
    });

    useEffect(() => {
        if (isHost) return;

        if (!authToken && !noAppRoutes.has(getUrlWithOutTrailingSlash(location.pathname))) {
            navigate(newRouter.buildUrl('auth.login'));
        }
    }, [authToken]);

    useEffect(() => {
        if (data && !data.verified) {
            pushNotification({
                message: t('not_verified'),
                type: 'success',
            });
        }
    }, [data]);

    useEffect(() => {
        if (isHost) return;

        if (isSuccess && data && noAppRoutes.has(getUrlWithOutTrailingSlash(location.pathname)))
            navigate(newRouter.buildUrl('app.user', { [URL_PARAMS.USER_NAME]: data.user_name }));

        if (isError) {
            navigate(newRouter.buildUrl('auth.login'));

            if (error && 'status' in error && error.status === 401) dispatch(clearAuthToken());
        }
    }, [isSuccess, data, isError, location.pathname]);

    if (authToken && isLoading)
        return (
            <AuthLayout>
                <TableContentSkeleton />
            </AuthLayout>
        );

    return element;
};

export default App;
