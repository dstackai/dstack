import React from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';

import { Box, SpaceBetween } from 'components';
import { UnauthorizedLayout } from 'layouts/UnauthorizedLayout';

import { LoginByOkta } from '../LoginByOkta';
import { LoginByTokenForm } from '../LoginByTokenForm';

import styles from './styles.module.scss';

export const EnterpriseLogin: React.FC = () => {
    const { t } = useTranslation();

    return (
        <UnauthorizedLayout>
            <div className={cn(styles.form)}>
                <SpaceBetween size="xl">
                    <Box variant="h1" textAlign="center">
                        {t('auth.sign_in_to_dstack_enterprise')}
                    </Box>

                    <LoginByTokenForm />
                    <LoginByOkta className={styles.okta} />
                </SpaceBetween>
            </div>
        </UnauthorizedLayout>
    );
};
