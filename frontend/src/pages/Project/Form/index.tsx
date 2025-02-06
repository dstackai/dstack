import React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button, Container, FormInput, FormUI, Header, SpaceBetween } from 'components';

import { useNotifications } from 'hooks';
import { isResponseServerError, isResponseServerFormFieldError } from 'libs';

import { IProps } from './types';
import { FieldPath } from 'react-hook-form/dist/types/path';

export const ProjectForm: React.FC<IProps> = ({ initialValues, onCancel, loading, onSubmit: onSubmitProp }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();

    const formMethods = useForm<IProject>({
        defaultValues: {
            ...initialValues,
        },
    });

    const { handleSubmit, control, setError, clearErrors } = formMethods;

    const onSubmit = (data: IProject) => {
        clearErrors();

        onSubmitProp(data).catch((errorResponse) => {
            const errorRequestData = errorResponse?.data;

            if (isResponseServerError(errorRequestData)) {
                errorRequestData.detail.forEach((error) => {
                    if (isResponseServerFormFieldError(error)) {
                        setError(error.loc.join('.') as FieldPath<IProject>, { type: 'custom', message: error.msg });
                    } else {
                        pushNotification({
                            type: 'error',
                            content: t('common.server_error', { error: error.msg }),
                        });
                    }
                });
            } else {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: errorResponse?.error ?? errorResponse }),
                });
            }
        });
    };

    return (
        <form onSubmit={handleSubmit(onSubmit)}>
            <FormUI
                actions={
                    <SpaceBetween direction="horizontal" size="xs">
                        <Button formAction="none" disabled={loading} variant="link" onClick={onCancel}>
                            {t('common.cancel')}
                        </Button>

                        <Button loading={loading} disabled={loading} variant="primary">
                            {t('common.save')}
                        </Button>
                    </SpaceBetween>
                }
            >
                <SpaceBetween size="l">
                    <Container header={<Header variant="h2">{t('projects.edit.general')}</Header>}>
                        <SpaceBetween size="l">
                            <FormInput
                                label={t('projects.edit.project_name')}
                                description={t('projects.edit.project_name_description')}
                                control={control}
                                name="project_name"
                                disabled={loading}
                                rules={{
                                    required: t('validation.required'),

                                    pattern: {
                                        value: /^[a-zA-Z0-9-_]+$/,
                                        message: t('projects.edit.validation.user_name_format'),
                                    },
                                }}
                            />
                        </SpaceBetween>
                    </Container>
                </SpaceBetween>
            </FormUI>
        </form>
    );
};
