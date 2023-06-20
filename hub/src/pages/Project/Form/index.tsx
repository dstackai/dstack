import React, { useMemo } from 'react';
import { DefaultValues, FormProvider, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import {
    Alert,
    Button,
    Container,
    FormField,
    FormInput,
    FormTiles,
    FormUI,
    Grid,
    Header,
    InfoLink,
    SpaceBetween,
    TilesProps,
} from 'components';

import { useHelpPanel, useNotifications } from 'hooks';
import { isRequestFormErrors2, isRequestFormFieldError } from 'libs';
import { useGetBackendTypesQuery } from 'services/project';

import { AWSBackend } from './AWS';
import { AzureBackend } from './Azure';
import { BACKEND_TYPE_HELP } from './constants';
import { GCPBackend } from './GCP';

import { BackendTypesEnum, IProps, TBackendOption } from './types';
import { FieldPath } from 'react-hook-form/dist/types/path';

export const ProjectForm: React.FC<IProps> = ({ initialValues, onCancel, loading, onSubmit: onSubmitProp }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const isEditing = !!initialValues;
    const [openHelpPanel] = useHelpPanel();

    const { data: backendTypesData } = useGetBackendTypesQuery();

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
                type: BackendTypesEnum.AWS,
            },
        };
    };

    const formMethods = useForm<IProject>({
        defaultValues: getDefaultValues(),
    });

    const { handleSubmit, control, watch, setError, reset, clearErrors } = formMethods;

    const backendType = watch('backend.type');
    const projectNameValue = watch('project_name');

    const backendOptions: TBackendOption[] = useMemo(() => {
        return Object.values(BackendTypesEnum).map((type) => {
            const disabled: boolean = loading || !backendTypesData;

            return {
                label: t(`projects.backend_type.${type}`),
                value: type,
                description: t(`projects.backend_type.${type}_description`),
                disabled,
            };
        });
    }, [backendTypesData, loading]);

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
            } else {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: errorResponse?.error ?? errorResponse }),
                });
            }
        });
    };

    const onChangeBackendType: TilesProps['onChange'] = ({ detail: { value } }) => {
        reset({
            project_name: projectNameValue,
            backend: {
                type: value as TProjectBackendType,
            },
        });
    };

    const renderUnsupportedBackedMessage = (backendName: string, backendTypeName: BackendTypesEnum) => {
        return (
            <Grid gridDefinition={[{ colspan: 8 }]}>
                <Alert statusIconAriaLabel="Info" header="Unsupported backend type">
                    Dependencies for {backendName} backend are not installed. Run{' '}
                    <code>pip install dstack[{backendTypeName}]</code> to enable {backendName} support.
                </Alert>
            </Grid>
        );
    };

    const renderBackendFields = () => {
        if (!backendTypesData) return null;

        if (backendTypesData.includes(backendType)) {
            switch (backendType) {
                case BackendTypesEnum.AWS: {
                    return <AWSBackend loading={loading} />;
                }
                case BackendTypesEnum.AZURE: {
                    return <AzureBackend loading={loading} />;
                }
                case BackendTypesEnum.GCP: {
                    return <GCPBackend loading={loading} />;
                }
                default:
                    return null;
            }
        } else {
            switch (backendType) {
                case BackendTypesEnum.AWS: {
                    return renderUnsupportedBackedMessage('AWS', BackendTypesEnum.AWS);
                }
                case BackendTypesEnum.AZURE: {
                    return renderUnsupportedBackedMessage('Azure', BackendTypesEnum.AZURE);
                }
                case BackendTypesEnum.GCP: {
                    return renderUnsupportedBackedMessage('GCP', BackendTypesEnum.GCP);
                }
                default:
                    return (
                        <Grid gridDefinition={[{ colspan: 8 }]}>
                            <Alert statusIconAriaLabel="Info" header="Unsupported backend type">
                                Local backend requires Docker. Ensure Docker daemon is running to enable Local backend support.
                            </Alert>
                        </Grid>
                    );
            }
        }
    };

    const getDisabledSubmitButton = () => {
        return loading || !backendTypesData || !backendTypesData.includes(backendType);
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

                            <Button loading={loading} disabled={getDisabledSubmitButton()} variant="primary">
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
                        )}

                        <Container header={<Header variant="h2">{t('projects.edit.backend')}</Header>}>
                            <FormField
                                info={<InfoLink onFollow={() => openHelpPanel(BACKEND_TYPE_HELP)} />}
                                label={t('projects.edit.backend_type')}
                                description={t('projects.edit.backend_type_description')}
                            />

                            <SpaceBetween size="l">
                                <Grid gridDefinition={[{ colspan: 8 }]}>
                                    <FormTiles
                                        control={control}
                                        onChange={onChangeBackendType}
                                        name="backend.type"
                                        items={backendOptions}
                                    />
                                </Grid>

                                {renderBackendFields()}
                            </SpaceBetween>
                        </Container>
                    </SpaceBetween>
                </FormUI>
            </form>
        </FormProvider>
    );
};
