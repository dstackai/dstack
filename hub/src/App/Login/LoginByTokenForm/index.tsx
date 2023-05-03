import React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button, FormInput, FormUI, SpaceBetween } from 'components';

import { useAppDispatch } from 'hooks';

import { setAuthData } from 'App/slice';

type FormValues = Pick<IUser, 'token'>;

export interface Props {
    className?: string;
}

export const LoginByTokenForm: React.FC<Props> = ({ className }) => {
    const { t } = useTranslation();
    const { handleSubmit, control } = useForm<FormValues>();
    const dispatch = useAppDispatch();
    const onSubmit = (data: FormValues) => {
        dispatch(setAuthData(data));
    };

    return (
        <div className={className}>
            <form onSubmit={handleSubmit(onSubmit)}>
                <FormUI
                    actions={
                        <SpaceBetween direction="horizontal" size="xs">
                            <Button variant="primary">{t('common.login')}</Button>
                        </SpaceBetween>
                    }
                >
                    <FormInput
                        label={t('users.token')}
                        placeholder={t('users.token')}
                        description={t('users.token_description')}
                        control={control}
                        name="token"
                        rules={{ required: t('validation.required') }}
                    />
                </FormUI>
            </form>
        </div>
    );
};
