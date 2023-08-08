import React, { useMemo } from 'react';
import { FormProvider, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Alert, Button, FormField, FormTiles, FormUI, Grid, InfoLink, SpaceBetween, TilesProps } from 'components';

import { useHelpPanel, useNotifications } from 'hooks';
import { isRequestFormErrors2, isRequestFormFieldError } from 'libs';
import { useGetBackendTypesQuery } from 'services/backend';

import { AWSBackend } from './AWS';
import { AzureBackend } from './Azure';
import { BACKEND_TYPE_HELP } from './constants';
import { GCPBackend } from './GCP';
import { LambdaBackend } from './Lambda';

import { BackendTypesEnum, IProps, TBackendOption } from './types';
import { FieldPath } from 'react-hook-form/dist/types/path';

export const BackendForm: React.FC<IProps> = ({ initialValues, onCancel, loading, onSubmit: onSubmitProp }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const [openHelpPanel] = useHelpPanel();

    const { data: backendTypesData } = useGetBackendTypesQuery();

    const formMethods = useForm<TBackendConfig>({
        defaultValues: {
            type: 'aws',
            ...initialValues,
        },
    });

    const { handleSubmit, control, watch, setError, reset, clearErrors } = formMethods;

    const backendType = watch('type');

    const backendOptions: TBackendOption[] = useMemo(() => {
        return Object.values(BackendTypesEnum).map((type) => {
            const disabled: boolean = loading || !backendTypesData;

            return {
                label: t(`backend.type.${type}`),
                value: type,
                description: t(`backend.type.${type}_description`),
                disabled,
            };
        });
    }, [backendTypesData, loading]);

    const onSubmit = (data: TBackendConfig) => {
        if (data.type === 'aws' && data.ec2_subnet_id === '') data.ec2_subnet_id = null;

        clearErrors();

        onSubmitProp(data).catch((errorResponse) => {
            const errorRequestData = errorResponse?.data;

            if (isRequestFormErrors2(errorRequestData)) {
                errorRequestData.detail.forEach((error) => {
                    if (isRequestFormFieldError(error)) {
                        setError(error.loc.join('.') as FieldPath<TBackendConfig>, { type: 'custom', message: error.msg });
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
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-ignore
            type: value,
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
                case BackendTypesEnum.LAMBDA: {
                    return <LambdaBackend loading={loading} />;
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
                case BackendTypesEnum.LAMBDA: {
                    return renderUnsupportedBackedMessage('Lambda', BackendTypesEnum.LAMBDA);
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
                    <FormField
                        info={<InfoLink onFollow={() => openHelpPanel(BACKEND_TYPE_HELP)} />}
                        label={t('projects.edit.backend_type')}
                        description={t('projects.edit.backend_type_description')}
                    />

                    <SpaceBetween size="l">
                        <Grid gridDefinition={[{ colspan: 8 }]}>
                            <FormTiles control={control} onChange={onChangeBackendType} name="type" items={backendOptions} />
                        </Grid>

                        {renderBackendFields()}
                    </SpaceBetween>
                </FormUI>
            </form>
        </FormProvider>
    );
};
