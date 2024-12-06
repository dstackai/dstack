import React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import cn from 'classnames';

import { Button, FormInput } from 'components';

import { useAppDispatch } from 'hooks';
import { useCheckAuthTokenMutation } from 'services/user';

import { setAuthData } from 'App/slice';

import styles from './styles.module.scss';

type FormValues = Pick<IUserWithCreds['creds'], 'token'>;

export interface Props {
    className?: string;
}

export const LoginByTokenForm: React.FC<Props> = ({ className }) => {
    const { t } = useTranslation();
    const { handleSubmit, control, setError } = useForm<FormValues>();
    const dispatch = useAppDispatch();
    const navigate = useNavigate();

    const [checkToken, { isLoading }] = useCheckAuthTokenMutation();
    const onSubmit = (data: FormValues) => {
        checkToken(data)
            .unwrap()
            .then(() => {
                dispatch(setAuthData(data));
                navigate('/');
            })
            .catch((error) => {
                if (error?.status === 401) {
                    setError('token', { type: 'custom', message: t('auth.invalid_token') });
                    return;
                }

                setError('token', { type: 'custom', message: t('common.server_error', { error: error?.msg }) });
            });
    };

    return (
        <div className={cn(styles.form, className)}>
            <form onSubmit={handleSubmit(onSubmit)}>
                <div className={styles.token}>
                    <div className={styles.fieldWrap}>
                        <FormInput
                            placeholder={t('users.token')}
                            constraintText={t('users.token_description')}
                            control={control}
                            name="token"
                            disabled={isLoading}
                            rules={{ required: t('validation.required') }}
                            autoComplete="off"
                        />
                    </div>

                    <div className={styles.buttonWrap}>
                        <Button disabled={isLoading} loading={isLoading} variant="primary">
                            {t('common.login')}
                        </Button>
                    </div>
                </div>
            </form>
        </div>
    );
};
