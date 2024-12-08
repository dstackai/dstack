import React from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Button, Link, NavigateLink, SpaceBetween } from 'components';
import { UnauthorizedLayout } from 'layouts/UnauthorizedLayout';

import { goToUrl } from 'libs';
import { ROUTES } from 'routes';
import { useGithubAuthorizeMutation } from 'services/auth';

import { ReactComponent as GithubIcon } from 'assets/icons/github.svg';
import styles from './styles.module.scss';

export const LoginByGithub: React.FC = () => {
    const { t } = useTranslation();

    const [githubAuthorize, { isLoading }] = useGithubAuthorizeMutation();

    const signInClick = () => {
        githubAuthorize()
            .unwrap()
            .then((data) => {
                goToUrl(data.authorization_url);
            })
            .catch(console.log);
    };

    return (
        <UnauthorizedLayout>
            <Box margin={{ vertical: 'xxxl' }} textAlign="center" color="inherit">
                <div className={styles.signIn}>
                    <Box variant="h1">{t('auth.sign_in_to_dstack')}</Box>

                    <Button onClick={signInClick} disabled={isLoading} loading={isLoading} variant="primary">
                        <span className={styles.loginButtonInner}>
                            <GithubIcon />
                            {t('common.login_github')}
                        </span>
                    </Button>

                    <div className={styles.links}>
                        <SpaceBetween size="xl" alignItems="center">
                            <Box color="text-body-secondary">
                                By clicking you agree to{' '}
                                <Link href="https://dstack.ai/terms/" target="_blank">
                                    Terms of service
                                </Link>{' '}
                                and{' '}
                                <Link href="https://dstack.ai/privacy/" target="_blank">
                                    Privacy policy
                                </Link>
                            </Box>
                            <Box color="text-body-secondary">
                                <NavigateLink href={ROUTES.AUTH.TOKEN}>{t('auth.login_by_token')}</NavigateLink>
                            </Box>
                        </SpaceBetween>
                    </div>
                </div>
            </Box>
        </UnauthorizedLayout>
    );
};
