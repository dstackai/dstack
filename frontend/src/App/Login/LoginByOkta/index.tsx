import React from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';

import { Button } from 'components';

import { goToUrl } from 'libs';
import { useOktaAuthorizeMutation, useOktaInfoQuery } from 'services/auth';

import { ReactComponent as OktaIcon } from 'assets/icons/okta.svg';
import styles from './styles.module.scss';

export const LoginByOkta: React.FC<{ className?: string }> = ({ className }) => {
    const { t } = useTranslation();

    const { data } = useOktaInfoQuery();
    const [oktaAuthorize, { isLoading }] = useOktaAuthorizeMutation();

    const signInClick = () => {
        oktaAuthorize()
            .unwrap()
            .then((data) => {
                goToUrl(data.authorization_url);
            })
            .catch(console.log);
    };

    if (!data?.enabled) {
        return null;
    }

    return (
        <div className={cn(styles.signIn, className)}>
            <Button onClick={signInClick} disabled={isLoading} loading={isLoading} variant="primary">
                <span className={styles.loginButtonInner}>
                    <OktaIcon />
                    {t('common.login_okta')}
                </span>
            </Button>
        </div>
    );
};
