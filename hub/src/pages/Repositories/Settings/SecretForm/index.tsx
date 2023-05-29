import React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button, FormInput, FormTextarea, FormUI, Modal, SpaceBetween } from 'components';

import { useNotifications } from 'hooks';
import { isRequestFormErrors2, isRequestFormFieldError } from 'libs';
import { useCreateSecretMutation, useUpdateSecretMutation } from 'services/secret';

import { FormValues, IProps } from './types';
import { FieldPath } from 'react-hook-form/dist/types/path';

export const SecretForm: React.FC<IProps> = ({ onClose, repoId, projectName, initialValues }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();

    const { handleSubmit, control, setError } = useForm<FormValues>({
        defaultValues: initialValues,
    });

    const [updateSecret, { isLoading: isUpdating }] = useUpdateSecretMutation();
    const [createSecret, { isLoading }] = useCreateSecretMutation();

    const loading = isLoading || isUpdating;

    const onSubmit = (values: FormValues) => {
        const action = initialValues?.secret_name ? updateSecret : createSecret;

        action({
            project_name: projectName,
            repo_id: repoId,
            secret: values,
        })
            .unwrap()
            .then(() => {
                if (onClose) onClose();
            })
            .catch((errorResponse) => {
                const errorRequestData = errorResponse?.data;

                if (isRequestFormErrors2(errorRequestData)) {
                    errorRequestData.detail.forEach((error) => {
                        if (isRequestFormFieldError(error)) {
                            setError(error.loc.join('.') as FieldPath<ISecret>, { type: 'custom', message: error.msg });
                        } else {
                            pushNotification({
                                type: 'error',
                                content: t('common.server_error', { error: error.msg }),
                            });
                        }
                    });
                }
            });
    };

    const onCancel = () => {
        if (onClose) onClose();
    };

    const onDismiss = () => {
        if (onClose) onClose();
    };

    return (
        <Modal
            onDismiss={onDismiss}
            visible
            closeAriaLabel="Close modal"
            header={t(`projects.repo.secrets.${initialValues ? 'update' : 'add'}_modal_title`)}
        >
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
                        <FormInput
                            label={t('projects.repo.secrets.name')}
                            description={t('projects.repo.secrets.name_description')}
                            control={control}
                            name="secret_name"
                            disabled={loading}
                            rules={{
                                required: t('validation.required'),
                            }}
                        />

                        <FormTextarea
                            label={t('projects.repo.secrets.value')}
                            description={t('projects.repo.secrets.value_description')}
                            control={control}
                            name="secret_value"
                            disabled={loading}
                            autoComplete="off"
                            rules={{
                                required: t('validation.required'),
                            }}
                        />
                    </SpaceBetween>
                </FormUI>
            </form>
        </Modal>
    );
};
