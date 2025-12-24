import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { NavigateLink } from 'components';
import { UnauthorizedLayout } from 'layouts/UnauthorizedLayout';

import { useAppDispatch } from 'hooks';
import { ROUTES } from 'routes';
import { useGetNextRedirectMutation, useGithubCallbackMutation } from 'services/auth';
import { useLazyGetProjectsQuery } from 'services/project';

import { AuthErrorMessage } from 'App/AuthErrorMessage';
import { Loading } from 'App/Loading';
import { setAuthData } from 'App/slice';

export const LoginByGithubCallback: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const [isInvalidCode, setIsInvalidCode] = useState(false);
    const dispatch = useAppDispatch();

    const [getNextRedirect] = useGetNextRedirectMutation();
    const [githubCallback] = useGithubCallbackMutation();
    const [getProjects] = useLazyGetProjectsQuery();

    const checkCode = () => {
        if (code && state) {
            getNextRedirect({ code: code, state: state })
                .unwrap()
                .then(async ({ redirect_url }) => {
                    if (redirect_url) {
                        window.location.href = redirect_url;
                        return;
                    }
                    githubCallback({ code, state })
                        .unwrap()
                        .then(async ({ creds: { token } }) => {
                            dispatch(setAuthData({ token }));
                            if (process.env.UI_VERSION === 'sky') {
                                const result = await getProjects().unwrap();
                                if (result?.length === 0) {
                                    navigate(ROUTES.PROJECT.ADD);
                                    return;
                                }
                            }
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
        if (code) {
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
