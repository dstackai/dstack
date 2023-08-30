import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import {
    Button,
    Container,
    FormCheckbox,
    FormField,
    FormInput,
    FormUI,
    Header,
    InfoLink,
    InputCSD,
    SpaceBetween,
    Spinner,
} from 'components';

import { useBreadcrumbs, useHelpPanel, useNotifications } from 'hooks';
import { isRequestFormErrors2, isRequestFormFieldError } from 'libs';
import { ROUTES } from 'routes';
import {
    useGetProjectGatewayQuery,
    useTestProjectGatewayDomainMutation,
    useUpdateProjectGatewayMutation,
} from 'services/gateway';

import { WILDCARD_DOMAIN_HELP } from './constants';

import { FieldPath } from 'react-hook-form/dist/types/path';

import styles from './styles.module.scss';

const FIELD_NAMES: Record<string, keyof TUpdateGatewayParams> = {
    WILDCARD_DOMAIN: 'wildcard_domain',
    DEFAULT: 'default',
};

export const EditGateway: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramInstanceName = params.instance ?? '';
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [openHelpPanel] = useHelpPanel();

    const { data, isLoading: isLoadingGateway } = useGetProjectGatewayQuery({
        projectName: paramProjectName,
        instanceName: paramInstanceName,
    });

    const [updateGateway, { isLoading: isUpdating }] = useUpdateProjectGatewayMutation();
    const [testDomain, { isLoading: isTesting }] = useTestProjectGatewayDomainMutation();

    const { handleSubmit, control, setError, clearErrors, watch, getValues, setValue } = useForm<TUpdateGatewayParams>({
        defaultValues: { [FIELD_NAMES.DEFAULT]: false },
    });
    const domainFieldValue = watch(FIELD_NAMES.WILDCARD_DOMAIN);

    useEffect(() => {
        if (data) {
            setValue(FIELD_NAMES.DEFAULT, data.default);
            setValue(FIELD_NAMES.WILDCARD_DOMAIN, data.head.wildcard_domain);
        }
    }, [data]);

    const isDisabledFields = isUpdating || isLoadingGateway;

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
            text: t('gateway.edit_gateway'),
            href: ROUTES.PROJECT.GATEWAY.EDIT.FORMAT(paramProjectName, paramInstanceName),
        },
    ]);

    const onTest = () => {
        clearErrors(FIELD_NAMES.WILDCARD_DOMAIN);

        testDomain({
            projectName: paramProjectName,
            instanceName: paramInstanceName,
            domain: getValues(FIELD_NAMES.WILDCARD_DOMAIN) as string,
        })
            .unwrap()
            .then(() =>
                pushNotification({
                    type: 'success',
                    content: t('gateway.test_domain.success_notification'),
                }),
            )
            .catch((errorResponse) => {
                const errorRequestData = errorResponse?.data;

                if (isRequestFormErrors2(errorRequestData)) {
                    setError(FIELD_NAMES.WILDCARD_DOMAIN, {
                        type: 'custom',
                        message: errorRequestData.detail[0].msg,
                    });
                } else {
                    pushNotification({
                        type: 'error',
                        content: t('common.server_error', {
                            error: errorRequestData?.detail?.msg,
                        }),
                    });
                }
            });
    };

    const onCancel = () => {
        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    const onSubmit = (values: TUpdateGatewayParams) => {
        updateGateway({
            projectName: paramProjectName,
            instanceName: paramInstanceName,
            values,
        })
            .unwrap()
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('gateway.update.success_notification'),
                });

                navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
            })
            .catch((errorResponse) => {
                const errorRequestData = errorResponse?.data;

                if (isRequestFormErrors2(errorRequestData)) {
                    errorRequestData.detail.forEach((error) => {
                        if (isRequestFormFieldError(error)) {
                            setError(error.loc.join('.') as FieldPath<TUpdateGatewayParams>, {
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
        if (isLoadingGateway)
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
                        <Button formAction="none" disabled={isUpdating || isTesting} variant="link" onClick={onCancel}>
                            {t('common.cancel')}
                        </Button>

                        <Button loading={isUpdating} disabled={isUpdating || isTesting} variant="primary">
                            {t('common.save')}
                        </Button>
                    </SpaceBetween>
                }
            >
                <SpaceBetween size="l">
                    <Container header={<Header variant="h2">{t('gateway.edit_gateway')}</Header>}>
                        <SpaceBetween size="l">
                            <FormField label={t('gateway.edit.backend')} secondaryControl={renderSpinner()}>
                                <InputCSD readOnly disabled={isDisabledFields} value={data?.backend ?? ''} />
                            </FormField>

                            <FormField label={t('gateway.edit.region')} secondaryControl={renderSpinner()}>
                                <InputCSD readOnly disabled={isDisabledFields} value={data?.head.region ?? ''} />
                            </FormField>

                            <FormField label={t('gateway.edit.external_ip')} secondaryControl={renderSpinner()}>
                                <InputCSD readOnly disabled={isDisabledFields} value={data?.head.external_ip ?? ''} />
                            </FormField>

                            <FormCheckbox
                                label={t('gateway.edit.default')}
                                checkboxLabel={t('gateway.edit.default_checkbox')}
                                control={control}
                                name={FIELD_NAMES.DEFAULT}
                                disabled={isDisabledFields}
                                secondaryControl={renderSpinner()}
                            />

                            <FormInput
                                info={<InfoLink onFollow={() => openHelpPanel(WILDCARD_DOMAIN_HELP)} />}
                                label={t('gateway.edit.wildcard_domain')}
                                description={t('gateway.edit.wildcard_domain_description')}
                                placeholder={t('gateway.edit.wildcard_domain_placeholder')}
                                control={control}
                                name={FIELD_NAMES.WILDCARD_DOMAIN}
                                disabled={isDisabledFields}
                                rules={{
                                    pattern: {
                                        value: /^\*\..+\..+/,
                                        message: t('gateway.edit.validation.wildcard_domain_format', {
                                            pattern: t('gateway.edit.wildcard_domain_placeholder'),
                                        }),
                                    },
                                }}
                                secondaryControl={
                                    renderSpinner() ?? (
                                        <Button formAction="none" disabled={isTesting || !domainFieldValue} onClick={onTest}>
                                            {t('common.test')}
                                        </Button>
                                    )
                                }
                            />
                        </SpaceBetween>
                    </Container>
                </SpaceBetween>
            </FormUI>
        </form>
    );
};
