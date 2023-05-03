import React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button, FormInput } from 'components';

import { useAppDispatch } from 'hooks';

import { setAuthData } from 'App/slice';

import styles from './styles.module.scss';

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
                <div className={styles.token}>
                    <div className={styles.fieldWrap}>
                        <FormInput
                            placeholder={t('users.token')}
                            constraintText={t('users.token_description')}
                            control={control}
                            name="token"
                            rules={{ required: t('validation.required') }}
                        />
                    </div>

                    <div className={styles.buttonWrap}>
                        <Button variant="primary">{t('common.login')}</Button>
                    </div>
                </div>
            </form>
        </div>
    );
};
