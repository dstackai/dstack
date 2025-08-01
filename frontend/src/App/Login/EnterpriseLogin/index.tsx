import React from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';

import { Box, NavigateLink, SpaceBetween } from 'components';
import { UnauthorizedLayout } from 'layouts/UnauthorizedLayout';

import { ROUTES } from 'routes';
import { useGetEntraInfoQuery, useGetGoogleInfoQuery, useGetOktaInfoQuery } from 'services/auth';

import { LoginByEntraID } from '../EntraID/LoginByEntraID';
import { LoginByGoogle } from '../LoginByGoogle';
import { LoginByOkta } from '../LoginByOkta';
import { LoginByTokenForm } from '../LoginByTokenForm';

import styles from './styles.module.scss';

export const EnterpriseLogin: React.FC = () => {
    const { t } = useTranslation();
    const { data: oktaData, isLoading: isLoadingOkta } = useGetOktaInfoQuery();
    const { data: entraData, isLoading: isLoadingEntra } = useGetEntraInfoQuery();
    const { data: googleData, isLoading: isLoadingGoogle } = useGetGoogleInfoQuery();

    const oktaEnabled = oktaData?.enabled;
    const entraEnabled = entraData?.enabled;
    const googleEnabled = googleData?.enabled;

    const isLoading = isLoadingOkta || isLoadingEntra;
    const isShowTokenForm = !oktaEnabled && !entraEnabled;

    return (
        <UnauthorizedLayout>
            <div className={cn(styles.form)}>
                <SpaceBetween size="xl" alignItems="center">
                    <Box variant="h1" textAlign="center">
                        {t('auth.sign_in_to_dstack_enterprise')}
                    </Box>

                    {!isLoading && isShowTokenForm && <LoginByTokenForm />}
                    {!isLoadingOkta && oktaEnabled && <LoginByOkta className={styles.okta} />}
                    {!isLoadingEntra && entraEnabled && <LoginByEntraID className={styles.entra} />}
                    {!isLoadingGoogle && googleEnabled && <LoginByGoogle className={styles.google} />}

                    {!isLoading && !isShowTokenForm && (
                        <Box color="text-body-secondary">
                            <NavigateLink href={ROUTES.AUTH.TOKEN}>{t('auth.login_by_token')}</NavigateLink>
                        </Box>
                    )}
                </SpaceBetween>
            </div>
        </UnauthorizedLayout>
    );
};
