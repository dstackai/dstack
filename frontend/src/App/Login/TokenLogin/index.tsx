import React from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';

import { Box, NavigateLink, SpaceBetween } from 'components';
import { UnauthorizedLayout } from 'layouts/UnauthorizedLayout';

import { ROUTES } from 'routes';

import { LoginByTokenForm } from '../LoginByTokenForm';

import styles from './styles.module.scss';

export const TokenLogin: React.FC = () => {
    const { t } = useTranslation();

    return (
        <UnauthorizedLayout>
            <div className={cn(styles.form)}>
                <SpaceBetween size="xl" alignItems="center">
                    <Box variant="h1" textAlign="center">
                        {t('auth.sign_in_to_dstack_enterprise')}
                    </Box>

                    <LoginByTokenForm />

                    <Box color="text-body-secondary">
                        <NavigateLink href={ROUTES.BASE}>{t('auth.another_login_methods')}</NavigateLink>
                    </Box>
                </SpaceBetween>
            </div>
        </UnauthorizedLayout>
    );
};
