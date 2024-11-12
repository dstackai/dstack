import React from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';

import { Box, SpaceBetween } from 'components';
import { UnauthorizedLayout } from 'layouts/UnauthorizedLayout';

import { useGetOktaInfoQuery } from 'services/auth';

import { LoginByOkta } from '../LoginByOkta';
import { LoginByTokenForm } from '../LoginByTokenForm';

import styles from './styles.module.scss';

export const EnterpriseLogin: React.FC = () => {
    const { t } = useTranslation();
    const { data } = useGetOktaInfoQuery();

    const oktaEnabled = data?.data?.enabled;

    return (
        <UnauthorizedLayout>
            <div className={cn(styles.form)}>
                <SpaceBetween size="xl" alignItems="center">
                    <Box variant="h1" textAlign="center">
                        {t('auth.sign_in_to_dstack_enterprise')}
                    </Box>

                    {data && !oktaEnabled && <LoginByTokenForm />}
                    {data && oktaEnabled && <LoginByOkta className={styles.okta} />}
                </SpaceBetween>
            </div>
        </UnauthorizedLayout>
    );
};
