import React, { useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import AuthPage from 'components/AuthPage';
import { useAppDispatch, useNotifications } from 'hooks';
import { getRouterModule, RouterModules } from 'route';
import { setAuthToken } from 'App/slice';

const errorCodeMap = {
    'not-registered': 'you_do_not_have_an_account_in_dstack',
};

const CreateSession: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const session = searchParams.get('session');
    const errorCode = searchParams.get('errorCode');
    const message = searchParams.get('message');
    const hasError = errorCode || errorCode === '';
    const { push: pushNotification, removeAll: removeAllNotifications } = useNotifications();
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);

    const dispatch = useAppDispatch();

    useEffect(() => {
        if (!hasError && session) {
            dispatch(setAuthToken(session));
            navigate(newRouter.buildUrl('app'));
        }
    }, [session, hasError, message]);

    useEffect(() => {
        removeAllNotifications();

        if (message)
            pushNotification({
                message: message,
                type: 'success',
            });
    }, []);

    if (!hasError) return null;

    return (
        <AuthPage>
            <AuthPage.Title>
                {errorCode
                    ? t(errorCodeMap[errorCode as keyof typeof errorCodeMap])
                    : t('you_do_not_have_an_account_in_dstack')}
            </AuthPage.Title>

            <AuthPage.SimpleText>
                <Link to={newRouter.buildUrl('app')}>{t('request_access')}</Link>
            </AuthPage.SimpleText>
        </AuthPage>
    );
};

export default CreateSession;
