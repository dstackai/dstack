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
import { getServerError, isResponseServerError, isResponseServerFormFieldError } from 'libs';
import { ROUTES } from 'routes';
import {
    useGetProjectGatewayQuery,
    useSetDefaultProjectGatewayMutation,
    useSetWildcardDomainOfGatewayMutation,
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
    const paramProjectName = params.projectName ?? '';
    const paramInstanceName = params.instance ?? '';
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [openHelpPanel] = useHelpPanel();

    const { data, isLoading: isLoadingGateway } = useGetProjectGatewayQuery({
        projectName: paramProjectName,
        instanceName: paramInstanceName,
    });

    const [setDefault, { isLoading: isSettingDefault }] = useSetDefaultProjectGatewayMutation();
    const [setWildcardDomainOfGateway, { isLoading: isUpdating }] = useSetWildcardDomainOfGatewayMutation();

    const { handleSubmit, control, watch, setValue, setError } = useForm<TUpdateGatewayParams>({
        defaultValues: { [FIELD_NAMES.DEFAULT]: false },
    });

    const isDefault = watch(FIELD_NAMES.DEFAULT);

    useEffect(() => {
        if (data) {
            setValue(FIELD_NAMES.DEFAULT, data.default);
            setValue(FIELD_NAMES.WILDCARD_DOMAIN, data.wildcard_domain);
        }
    }, [data]);

    const isDisabledFields = isUpdating || isLoadingGateway;

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
            text: t('gateway.edit_gateway'),
            href: ROUTES.PROJECT.GATEWAY.EDIT.FORMAT(paramProjectName, paramInstanceName),
        },
    ]);

    const onCancel = () => {
        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    const onChangeDefault = () => {
        setDefault({
            projectName: paramProjectName,
            name: paramInstanceName,
        })
            .unwrap()
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('gateway.update.success_notification'),
                });
            });
    };

    const onSubmit = ({ wildcard_domain }: TUpdateGatewayParams) => {
        setWildcardDomainOfGateway({
            projectName: paramProjectName,
            name: paramInstanceName,
            wildcard_domain,
        })
            .unwrap()
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('gateway.update.success_notification'),
                });
            })
            .catch((errorResponse) => {
                const errorRequestData = errorResponse?.data;

                if (isResponseServerError(errorRequestData)) {
                    errorRequestData.detail.forEach((error) => {
                        if (isResponseServerFormFieldError(error)) {
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
                            error: getServerError(errorResponse),
                        }),
                    });
                }
            });
    };

    const renderSpinner = (force?: boolean) => {
        if (isLoadingGateway || force)
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
                        <Button formAction="none" disabled={isUpdating} variant="link" onClick={onCancel}>
                            {t('common.cancel')}
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
                                <InputCSD readOnly disabled={isDisabledFields} value={data?.region ?? ''} />
                            </FormField>

                            <FormField label={t('gateway.edit.external_ip')} secondaryControl={renderSpinner()}>
                                <InputCSD readOnly disabled={isDisabledFields} value={data?.ip_address ?? ''} />
                            </FormField>

                            <FormCheckbox
                                label={t('gateway.edit.default')}
                                checkboxLabel={t('gateway.edit.default_checkbox')}
                                control={control}
                                name={FIELD_NAMES.DEFAULT}
                                disabled={!!isDefault || isSettingDefault}
                                secondaryControl={renderSpinner(isSettingDefault)}
                                onChange={onChangeDefault}
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
                                        <Button loading={isUpdating} disabled={isUpdating} variant="primary">
                                            {t('common.save')}
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
