import React from 'react';
import { useTranslation } from 'react-i18next';
import { Container, Header, FormUI, SpaceBetween, Button, FormInput, FormTiles } from 'components';
import { useForm, FormProvider } from 'react-hook-form';
import { IProps, TBackendOption } from './types';
import { AWSBackend } from './AWS';

export const HubForm: React.FC<IProps> = ({ initialValues, onCancel, loading, onSubmit: onSubmitProp }) => {
    const { t } = useTranslation();
    const isEditing = !!initialValues;

    const formMethods = useForm<IHub>({
        defaultValues: initialValues ?? {
            backend: {
                type: 'aws',
            },
        },
    });

    const { handleSubmit, control, watch } = formMethods;

    const backendType = watch('backend.type');

    const backendOptions: TBackendOption[] = [
        {
            label: t('hubs.backend_type.aws'),
            value: 'aws',
            description: t('hubs.backend_type.aws_description'),
            disabled: loading,
        },
        {
            label: t('hubs.backend_type.gcp'),
            value: 'gcp',
            description: t('hubs.backend_type.gcp_description'),
            disabled: true,
        },
        {
            label: t('hubs.backend_type.azure'),
            value: 'azure',
            description: t('hubs.backend_type.azure_description'),
            disabled: true,
        },
    ];

    const onSubmit = (data: IHub) => {
        onSubmitProp(data);
    };

    const renderBackendFields = () => {
        switch (backendType) {
            case 'aws': {
                return <AWSBackend loading={loading} />;
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
                            <Container header={<Header variant="h2">{t('hubs.edit.general')}</Header>}>
                                <SpaceBetween size="l">
                                    <FormInput
                                        label={t('hubs.edit.hub_name')}
                                        control={control}
                                        name="hub_name"
                                        disabled={loading}
                                    />
                                </SpaceBetween>
                            </Container>
                        )}

                        <Container header={<Header variant="h2">{t('hubs.edit.backend')}</Header>}>
                            <SpaceBetween size="l">
                                <FormTiles control={control} name="backend.type" items={backendOptions} />
                                {renderBackendFields()}
                            </SpaceBetween>
                        </Container>
                    </SpaceBetween>
                </FormUI>
            </form>
        </FormProvider>
    );
};
