import React, { useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Button, Container, FormSelect, FormSelectOptions, FormUI, Header, SpaceBetween, Spinner } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useCreateProjectGatewayMutation, useGetProjectGatewayBackendsQuery } from 'services/gateway';

import { isRequestFormErrors2, isRequestFormFieldError } from '../../../../libs';

import { FieldPath } from 'react-hook-form/dist/types/path';

import styles from './styles.module.scss';

const FIELD_NAMES: Record<string, keyof TCreateGatewayParams> = {
    BACKEND: 'backend',
    REGION: 'region',
};

export const AddGateway: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();

    const { data, isLoading: isLoadingBackends } = useGetProjectGatewayBackendsQuery({
        projectName: paramProjectName,
    });

    const [createGateway, { isLoading: isCreating }] = useCreateProjectGatewayMutation();

    const { handleSubmit, control, watch, setError } = useForm<TCreateGatewayParams>();

    const backendFormValue = watch(FIELD_NAMES.BACKEND);

    const isDisabledFields = isCreating || isLoadingBackends;

    useBreadcrumbs([
        {
            text: t('navigation.projects'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            text: t('projects.settings'),
            href: ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName),
        },
        {
            text: t('gateway.add_gateway'),
            href: ROUTES.PROJECT.GATEWAY.ADD.FORMAT(paramProjectName),
        },
    ]);

    const backendOptions: FormSelectOptions = data?.map((i) => ({ label: i.backend, value: i.backend })) ?? [];

    const regionOptions: FormSelectOptions = useMemo(() => {
        if (!data || !backendFormValue) return [];

        const backend = data.find((b) => b.backend === backendFormValue)!;

        return backend.regions.map((region) => ({ label: region, value: region }));
    }, [backendFormValue]);

    const onCancel = () => {
        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    const onSubmit = (gateway: TCreateGatewayParams) => {
        createGateway({
            projectName: paramProjectName,
            gateway,
        })
            .unwrap()
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('gateway.create.success_notification'),
                });

                navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
            })
            .catch((errorResponse) => {
                const errorRequestData = errorResponse?.data;

                if (isRequestFormErrors2(errorRequestData)) {
                    errorRequestData.detail.forEach((error) => {
                        if (isRequestFormFieldError(error)) {
                            setError(error.loc.join('.') as FieldPath<TCreateGatewayParams>, {
                                type: 'custom',
                                message: error.msg,
                            });
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
                        content: t('common.server_error', {
                            error: errorResponse?.data?.detail?.map((i: { msg: string }) => i.msg).join(', '),
                        }),
                    });
                }
            });
    };

    const renderSpinner = () => {
        if (isLoadingBackends)
            return (
                <div className={styles.fieldSpinner}>
                    <Spinner />
                </div>
            );
    };

    return (
        <form onSubmit={handleSubmit(onSubmit)}>
            <FormUI
                actions={
                    <SpaceBetween direction="horizontal" size="xs">
                        <Button formAction="none" disabled={isCreating} variant="link" onClick={onCancel}>
                            {t('common.cancel')}
                        </Button>

                        <Button loading={isCreating} disabled={isCreating} variant="primary">
                            {t('common.save')}
                        </Button>
                    </SpaceBetween>
                }
            >
                <SpaceBetween size="l">
                    <Container header={<Header variant="h2">{t('gateway.add_gateway')}</Header>}>
                        <SpaceBetween size="l">
                            <FormSelect
                                label={t('gateway.edit.backend')}
                                description={t('gateway.edit.backend_description')}
                                control={control}
                                name={FIELD_NAMES.BACKEND}
                                disabled={isDisabledFields}
                                rules={{
                                    required: t('validation.required'),
                                }}
                                options={backendOptions}
                                secondaryControl={renderSpinner()}
                            />

                            <FormSelect
                                label={t('gateway.edit.region')}
                                description={t('gateway.edit.region_description')}
                                control={control}
                                name={FIELD_NAMES.REGION}
                                disabled={isDisabledFields || !backendFormValue}
                                options={regionOptions}
                                secondaryControl={renderSpinner()}
                            />
                        </SpaceBetween>
                    </Container>
                </SpaceBetween>
            </FormUI>
        </form>
    );
};
