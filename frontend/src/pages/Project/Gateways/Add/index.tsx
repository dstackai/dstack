import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { get as _get } from 'lodash';

import { Button, Container, FormSelect, FormSelectOptions, FormUI, Header, SpaceBetween, Spinner } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { getServerError, isResponseServerError, isResponseServerFormFieldError } from 'libs';
import { ROUTES } from 'routes';
import { useCreateProjectGatewayMutation } from 'services/gateway';
import { useGetProjectQuery } from 'services/project';

import { FieldPath } from 'react-hook-form/dist/types/path';

import styles from './styles.module.scss';

const FIELD_NAMES: Record<string, keyof TCreateGatewayParams> = {
    BACKEND: 'backend_type',
    REGION: 'region',
};

export const AddGateway: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [pushPermanentNotification] = useNotifications({ temporary: false });
    const [regionOptions, setRegionOptions] = useState<FormSelectOptions>([]);

    const { data, isLoading: isLoadingBackends } = useGetProjectQuery({ name: paramProjectName });

    const [createGateway, { isLoading: isCreating }] = useCreateProjectGatewayMutation();

    const { handleSubmit, control, watch, setValue, setError } = useForm<TCreateGatewayParams>();

    const backendFormValue = watch(FIELD_NAMES.BACKEND);

    const isDisabledFields = isCreating || isLoadingBackends;

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.FORMAT(paramProjectName),
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

    const backendOptions: FormSelectOptions =
        data?.backends.filter((b) => b.name !== 'dstack').map((i) => ({ label: i.name, value: i.name })) ?? [];

    useEffect(() => {
        if (data && backendFormValue) {
            const backend = data.backends.find((b) => b.name === backendFormValue);

            setRegionOptions(() => {
                if (!backend) return [];

                const regions = _get(backend.config, 'regions', _get(backend.config, 'locations', []));

                if (regions?.[0]) {
                    setValue(FIELD_NAMES.REGION, regions[0]);
                }

                return regions?.map((region) => ({ label: region, value: region })) ?? [];
            });
        } else {
            setRegionOptions([]);
        }
    }, [backendFormValue]);

    const onCancel = () => {
        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    const onSubmit = (gateway: TCreateGatewayParams) => {
        pushPermanentNotification({
            type: 'info',
            content: t('gateway.create.creating_notification'),
        });

        createGateway({
            projectName: paramProjectName,
            gateway,
        })
            .unwrap()
            .then((response) => {
                pushNotification({
                    type: 'success',
                    content: t('gateway.create.success_notification'),
                });

                navigate(ROUTES.PROJECT.GATEWAY.EDIT.FORMAT(paramProjectName, response.name));
            })
            .catch((errorResponse) => {
                const errorRequestData = errorResponse?.data;

                if (isResponseServerError(errorRequestData)) {
                    errorRequestData.detail.forEach((error) => {
                        if (isResponseServerFormFieldError(error)) {
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
                            error: getServerError(errorResponse),
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
                                rules={{
                                    required: t('validation.required'),
                                }}
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
