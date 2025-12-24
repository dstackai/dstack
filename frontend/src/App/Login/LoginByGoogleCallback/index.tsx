import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { NavigateLink } from 'components';
import { UnauthorizedLayout } from 'layouts/UnauthorizedLayout';

import { useAppDispatch } from 'hooks';
import { ROUTES } from 'routes';
import { useGetNextRedirectMutation, useGoogleCallbackMutation } from 'services/auth';

import { AuthErrorMessage } from 'App/AuthErrorMessage';
import { Loading } from 'App/Loading';
import { setAuthData } from 'App/slice';

export const LoginByGoogleCallback: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const [isInvalidCode, setIsInvalidCode] = useState(false);
    const dispatch = useAppDispatch();

    const [getNextRedirect] = useGetNextRedirectMutation();
    const [googleCallback] = useGoogleCallbackMutation();

    const checkCode = () => {
        if (code && state) {
            getNextRedirect({ code, state })
                .unwrap()
                .then(({ redirect_url }) => {
                    if (redirect_url) {
                        window.location.href = redirect_url;
                        return;
                    }
                    googleCallback({ code, state })
                        .unwrap()
                        .then(({ creds: { token } }) => {
                            dispatch(setAuthData({ token }));
                            navigate('/');
                        })
                        .catch(() => {
                            setIsInvalidCode(true);
                        });
                })
                .catch(() => {
                    setIsInvalidCode(true);
                });
        }
    };

    useEffect(() => {
        if (code && state) {
            checkCode();
        } else {
            setIsInvalidCode(true);
        }
    }, []);

    if (isInvalidCode)
        return (
            <UnauthorizedLayout>
                <AuthErrorMessage title={t('auth.authorization_failed')}>
                    <NavigateLink href={ROUTES.BASE}>{t('auth.try_again')}</NavigateLink>
                </AuthErrorMessage>
            </UnauthorizedLayout>
        );

    return (
        <UnauthorizedLayout>
            <Loading />;
        </UnauthorizedLayout>
    );
};
