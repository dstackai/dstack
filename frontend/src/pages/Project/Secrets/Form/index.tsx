import React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Box, Button, FormInput, FormTextarea, SpaceBetween } from 'components';

import { TFormValues } from '../types';

export type IFormProps = {
    initialValues?: TFormValues;
    onSubmit: (values: TFormValues) => void;
    onCancel?: () => void;
    loading?: boolean;
};

export const SecretForm: React.FC<IFormProps> = ({ initialValues, onSubmit: onSubmitProp, loading, onCancel }) => {
    const { t } = useTranslation();
    const { handleSubmit, control } = useForm<TFormValues>({
        defaultValues: {
            ...initialValues,
        },
    });

    const onSubmit = (values: TFormValues) => onSubmitProp(values);

    return (
        <form onSubmit={handleSubmit(onSubmit)}>
            <SpaceBetween direction="vertical" size="l">
                <FormInput
                    label={t('projects.edit.secrets.name')}
                    control={control}
                    name="name"
                    disabled={loading || !!initialValues?.id}
                    rules={{
                        required: t('validation.required'),

                        pattern: {
                            value: /^[A-Za-z0-9-_]{1,200}$/,
                            message: t('projects.edit.secrets.validation.secret_name_format'),
                        },
                    }}
                />

                <FormTextarea
                    rows={6}
                    label={t('projects.edit.secrets.value')}
                    control={control}
                    name="value"
                    disabled={loading}
                    rules={{
                        required: t('validation.required'),
                    }}
                />

                <Box float="right">
                    <SpaceBetween size="l" direction="horizontal">
                        {onCancel && (
                            <Button formAction="none" disabled={loading} onClick={onCancel}>
                                {t('common.cancel')}
                            </Button>
                        )}

                        <Button variant="primary" formAction="submit" loading={loading} disabled={loading}>
                            {t('common.save')}
                        </Button>
                    </SpaceBetween>
                </Box>
            </SpaceBetween>
        </form>
    );
};
