import React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button, FormInput, SpaceBetween } from 'components';

import { useAppDispatch } from 'hooks';
import { useCheckAuthTokenMutation } from 'services/user';

import { setAuthData } from 'App/slice';

type FormValues = Pick<IUserWithCreds['creds'], 'token'>;

export const LoginByTokenForm: React.FC = () => {
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
                if (error?.status === 401 || error?.status === 403) {
                    setError('token', { type: 'custom', message: t('auth.invalid_token') });
                    return;
                }

                setError('token', { type: 'custom', message: t('common.server_error', { error: error?.msg }) });
            });
    };

    return (
        <form onSubmit={handleSubmit(onSubmit)}>
            <SpaceBetween size="l">
                <FormInput
                    label={t('users.token')}
                    placeholder={t('users.token')}
                    constraintText="Use your personal access token"
                    control={control}
                    name="token"
                    disabled={isLoading}
                    rules={{ required: t('validation.required') }}
                    autoComplete="off"
                />
                <Button disabled={isLoading} loading={isLoading} variant="primary" fullWidth>
                    {t('common.continue')}
                </Button>
            </SpaceBetween>
        </form>
    );
};
