import React from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';

import { Button } from 'components';

import { goToUrl } from 'libs';
import { useEntraAuthorizeMutation } from 'services/auth';

import { getBaseUrl } from 'App/helpers';

import { ReactComponent as EntraIdIcon } from 'assets/icons/entraID.svg';
import styles from './styles.module.scss';

export const LoginByEntraID: React.FC<{ className?: string }> = ({ className }) => {
    const { t } = useTranslation();

    const [entraAuthorize, { isLoading }] = useEntraAuthorizeMutation();

    const signInClick = () => {
        entraAuthorize({ base_url: getBaseUrl() })
            .unwrap()
            .then((data) => {
                goToUrl(data.authorization_url);
            })
            .catch(console.log);
    };

    return (
        <div className={cn(styles.entraSignIn, className)}>
            <Button onClick={signInClick} disabled={isLoading} loading={isLoading} variant="primary">
                <span className={styles.loginButtonInner}>
                    <EntraIdIcon />
                    <span className={styles.loginButtonLabel}>{t('common.login_entra')}</span>
                </span>
            </Button>
        </div>
    );
};
