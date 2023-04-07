import React from 'react';
import { useTranslation } from 'react-i18next';
import { Container, Header, FormUI, SpaceBetween, Button, FormInput, FormRadioButtons } from 'components';
import { useForm, FormProvider, DefaultValues } from 'react-hook-form';
import { FieldPath } from 'react-hook-form/dist/types/path';
import { useNotifications } from 'hooks';
import { isRequestFormErrors2, isRequestFormFieldError } from 'libs';
import { IProps, TBackendOption } from './types';
import { AWSBackend } from './AWS';
import { GCPBackend } from './GCP';

export const ProjectForm: React.FC<IProps> = ({ initialValues, onCancel, loading, onSubmit: onSubmitProp }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const isEditing = !!initialValues;

    const getDefaultValues = (): DefaultValues<IProject> => {
        if (initialValues) {
            return {
                ...initialValues,
                backend: {
                    ...initialValues.backend,
                    ...(initialValues.backend.ec2_subnet_id === null ? { ec2_subnet_id: '' } : {}),
                },
            };
        }

        return {
            backend: {
                type: 'aws',
            },
        };
    };

    const formMethods = useForm<IProject>({
        defaultValues: getDefaultValues(),
    });

    const { handleSubmit, control, watch, setError, clearErrors } = formMethods;

    const backendType = watch('backend.type');

    const backendOptions: TBackendOption[] = [
        {
            label: t('projects.backend_type.aws'),
            value: 'aws',
            description: t('projects.backend_type.aws_description'),
            disabled: loading,
        },
        {
            label: t('projects.backend_type.gcp'),
            value: 'gcp',
            description: t('projects.backend_type.gcp_description'),
            disabled: loading,
        },
        // {
        //     label: t('projects.backend_type.azure'),
        //     value: 'azure',
        //     description: t('projects.backend_type.azure_description'),
        //     disabled: loading,
        // },
    ];

    const onSubmit = (data: IProject) => {
        if (data.backend.type === 'aws' && data.backend.ec2_subnet_id === '') data.backend.ec2_subnet_id = null;

        clearErrors();

        onSubmitProp(data).catch((errorResponse) => {
            const errorRequestData = errorResponse?.data;

            if (isRequestFormErrors2(errorRequestData)) {
                errorRequestData.detail.forEach((error) => {
                    if (isRequestFormFieldError(error)) {
                        setError(error.loc.join('.') as FieldPath<IProject>, { type: 'custom', message: error.msg });
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

    const renderBackendFields = () => {
        switch (backendType) {
            case 'aws': {
                return <AWSBackend loading={loading} />;
            }
            case 'gcp': {
                return <GCPBackend loading={loading} />;
            }
            default:
                return null;
        }
    };

    return (
        <FormProvider {...formMethods}>
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
                        {!isEditing && (
                            <Container header={<Header variant="h2">{t('projects.edit.general')}</Header>}>
                                <SpaceBetween size="l">
                                    <FormInput
                                        label={t('projects.edit.project_name')}
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
                        )}

                        <Container header={<Header variant="h2">{t('projects.edit.backend')}</Header>}>
                            <SpaceBetween size="l">
                                <FormRadioButtons
                                    label={t('projects.edit.backend_type')}
                                    control={control}
                                    name="backend.type"
                                    items={backendOptions}
                                />

                                {renderBackendFields()}
                            </SpaceBetween>
                        </Container>
                    </SpaceBetween>
                </FormUI>
            </form>
        </FormProvider>
    );
};
