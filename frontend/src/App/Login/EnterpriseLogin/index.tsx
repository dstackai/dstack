import React from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';

import { Box, NavigateLink, SpaceBetween } from 'components';
import { UnauthorizedLayout } from 'layouts/UnauthorizedLayout';

import { ROUTES } from 'routes';
import { useGetOktaInfoQuery } from 'services/auth';

import { LoginByOkta } from '../LoginByOkta';
import { LoginByTokenForm } from '../LoginByTokenForm';

import styles from './styles.module.scss';

export const EnterpriseLogin: React.FC = () => {
    const { t } = useTranslation();
    const { data, isLoading } = useGetOktaInfoQuery();

    const oktaEnabled = data?.enabled;

    return (
        <UnauthorizedLayout>
            <div className={cn(styles.form)}>
                <SpaceBetween size="xl" alignItems="center">
                    <Box variant="h1" textAlign="center">
                        {t('auth.sign_in_to_dstack_enterprise')}
                    </Box>

                    {!isLoading && !oktaEnabled && <LoginByTokenForm />}
                    {!isLoading && oktaEnabled && <LoginByOkta className={styles.okta} />}

                    {!isLoading && oktaEnabled && (
                        <Box color="text-body-secondary">
                            <NavigateLink href={ROUTES.AUTH.TOKEN}>{t('auth.login_by_token')}</NavigateLink>
                        </Box>
                    )}
                </SpaceBetween>
            </div>
        </UnauthorizedLayout>
    );
};
