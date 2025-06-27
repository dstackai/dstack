import React from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';

import { Button } from 'components';

import { goToUrl } from 'libs';
import { useGoogleAuthorizeMutation } from 'services/auth';

import { ReactComponent as GoogleIcon } from 'assets/icons/google.svg';
import styles from './styles.module.scss';

export const LoginByGoogle: React.FC<{ className?: string }> = ({ className }) => {
    const { t } = useTranslation();

    const [googleAuthorize, { isLoading }] = useGoogleAuthorizeMutation();

    const signInClick = () => {
        googleAuthorize()
            .unwrap()
            .then((data) => {
                goToUrl(data.authorization_url);
            })
            .catch(console.log);
    };

    return (
        <div className={cn(styles.signIn, className)}>
            <Button onClick={signInClick} disabled={isLoading} loading={isLoading} variant="normal">
                <span className={styles.loginButtonInner}>
                    <GoogleIcon />
                    <span className={styles.loginButtonLabel}>{t('common.login_google')}</span>
                </span>
            </Button>
        </div>
    );
};
