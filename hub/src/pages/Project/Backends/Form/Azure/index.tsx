import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { debounce } from 'lodash';

import {
    FormInput,
    FormMultiselect,
    FormMultiselectOptions,
    FormSelect,
    FormSelectOptions,
    InfoLink,
    SpaceBetween,
    Spinner,
} from 'components';

import { useHelpPanel, useNotifications } from 'hooks';
import useIsMounted from 'hooks/useIsMounted';
import { isRequestFormErrors2, isRequestFormFieldError } from 'libs';
import { useBackendValuesMutation } from 'services/backend';
import { AzureCredentialTypeEnum } from 'types';

import { CREDENTIALS_HELP, FIELD_NAMES, LOCATIONS_HELP, STORAGE_ACCOUNT_HELP, SUBSCRIPTION_HELP } from './constants';

import { IProps } from './types';

import styles from './styles.module.scss';

const FIELDS_QUEUE = [FIELD_NAMES.SUBSCRIPTION_ID, FIELD_NAMES.LOCATIONS, FIELD_NAMES.STORAGE_ACCOUNT];

export const AzureBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const { control, getValues, setValue, setError, clearErrors, watch } = useFormContext();
    const [valuesData, setValuesData] = useState<IAzureBackendValues | undefined>();
    const [subscriptionIds, setSubscriptionIds] = useState<FormSelectOptions>([]);
    const [tenantIds, setTenantIds] = useState<FormSelectOptions>([]);
    const [locations, setLocations] = useState<FormMultiselectOptions>([]);
    const [storageAccounts, setStorageAccounts] = useState<FormSelectOptions>([]);
    const [availableDefaultCredentials, setAvailableDefaultCredentials] = useState<boolean | null>(null);
    const lastUpdatedField = useRef<string | null>(null);
    const isFirstRender = useRef<boolean>(true);
    const isMounted = useIsMounted();

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();

    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);

    const [openHelpPanel] = useHelpPanel();

    const tenantIdValue = watch(FIELD_NAMES.TENANT_ID);
    const clientIdValue = watch(FIELD_NAMES.CREDENTIALS.CLIENT_ID);
    const clientSecretValue = watch(FIELD_NAMES.CREDENTIALS.CLIENT_SECRET);
    const credentialTypeValue = watch(FIELD_NAMES.CREDENTIALS.TYPE);

    const changeFormHandler = async () => {
        const formValues = getValues();
        const backendCredentials = formValues?.credentials ?? {};

        if (
            backendCredentials.type === AzureCredentialTypeEnum.CLIENT &&
            (!formValues.tenant_id || !backendCredentials.client_id || !backendCredentials.client_secret)
        ) {
            return;
        }

        if (formValues?.credentials && !formValues.credentials.type) delete formValues.credentials;

        clearErrors();

        try {
            const request = getBackendValues(formValues);
            requestRef.current = request;
            const response = await request.unwrap();

            if (!isMounted()) return;

            setValuesData(response);
            lastUpdatedField.current = null;

            setAvailableDefaultCredentials(response.default_credentials);

            // select authorization option
            if (!backendCredentials.type) {
                setValue(
                    FIELD_NAMES.CREDENTIALS.TYPE,
                    response.default_credentials ? AzureCredentialTypeEnum.DEFAULT : AzureCredentialTypeEnum.CLIENT,
                );

                if (response.default_credentials) changeFormHandler().catch(console.log);
            }

            // TENANT_ID available for only client credentials type
            if (response.tenant_id?.selected) {
                setValue(FIELD_NAMES.TENANT_ID, response.tenant_id.selected);
            }

            if (response.tenant_id?.values) {
                setTenantIds(response.tenant_id?.values);
            }

            if (response.subscription_id?.values) {
                setSubscriptionIds(response.subscription_id.values);
            }

            if (response.subscription_id?.selected !== undefined) {
                setValue(FIELD_NAMES.SUBSCRIPTION_ID, response.subscription_id.selected);
            }
            if (response.locations?.values) {
                setLocations(response.locations.values);
            }
            if (response.locations?.selected !== undefined) {
                setValue(FIELD_NAMES.LOCATIONS, response.locations.selected);
            }
            if (response.storage_account?.values) {
                setStorageAccounts(response.storage_account.values);
            }
            if (response.storage_account?.selected !== undefined) {
                setValue(FIELD_NAMES.STORAGE_ACCOUNT, response.storage_account.selected);
            }
        } catch (errorResponse) {
            console.log('fetch backends values error:', errorResponse);
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-ignore
            const errorRequestData = errorResponse?.data;

            if (isRequestFormErrors2(errorRequestData)) {
                errorRequestData.detail.forEach((error) => {
                    if (isRequestFormFieldError(error)) {
                        setError(error.loc.join('.'), { type: 'custom', message: error.msg });
                    } else {
                        pushNotification({
                            type: 'error',
                            content: t('common.server_error', { error: error?.msg }),
                        });
                    }
                });
            }
        }
    };

    useEffect(() => {
        if (!isFirstRender.current) return;

        changeFormHandler().catch(console.log);
        isFirstRender.current = false;
    }, []);

    const debouncedChangeFormHandler = useCallback(debounce(changeFormHandler, 1000), []);

    const onChangeCredentialField = () => {
        clearFields(0);
        if (requestRef.current) requestRef.current.abort();
        debouncedChangeFormHandler();
    };

    const onChangeCredentialsTypeField = () => {
        clearFields(0);
        if (requestRef.current) requestRef.current.abort();
        changeFormHandler().catch(console.log);
    };

    const clearFields = (startIndex: number) => {
        for (let i = startIndex; i < FIELDS_QUEUE.length; i++) {
            setValue(FIELDS_QUEUE[i], null);
        }
    };

    const getOnChangeSelectField = (fieldName: string) => () => {
        lastUpdatedField.current = fieldName;
        if (requestRef.current) requestRef.current.abort();
        changeFormHandler().catch(console.log);
    };

    const renderSpinner = (force?: boolean) => {
        if (isLoadingValues || force)
            return (
                <div className={styles.fieldSpinner}>
                    <Spinner />
                </div>
            );
    };

    const getDisabledByFieldName = (fieldName: string) => {
        let disabledField = loading || !credentialTypeValue;

        disabledField =
            disabledField ||
            (credentialTypeValue === AzureCredentialTypeEnum.CLIENT &&
                (!tenantIdValue || !clientIdValue || !clientSecretValue || !valuesData));

        disabledField = disabledField || (lastUpdatedField.current !== fieldName && isLoadingValues);

        switch (fieldName) {
            case FIELD_NAMES.SUBSCRIPTION_ID:
                disabledField = disabledField || !subscriptionIds.length;
                break;
            case FIELD_NAMES.LOCATIONS:
                disabledField = disabledField || !locations.length;
                break;
            case FIELD_NAMES.STORAGE_ACCOUNT:
                disabledField = disabledField || !storageAccounts.length;
                break;
        }

        return disabledField;
    };

    const renderTenantIdField = () => {
        if (credentialTypeValue === AzureCredentialTypeEnum.CLIENT)
            return (
                <FormInput
                    info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                    label={t('projects.edit.azure.tenant_id')}
                    description={t('projects.edit.azure.tenant_id_description')}
                    control={control}
                    name={FIELD_NAMES.TENANT_ID}
                    onChange={onChangeCredentialField}
                    disabled={loading}
                    rules={{ required: t('validation.required') }}
                />
            );

        if (credentialTypeValue === AzureCredentialTypeEnum.DEFAULT)
            return (
                <FormSelect
                    info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                    label={t('projects.edit.azure.tenant_id')}
                    description={t('projects.edit.azure.tenant_id_description')}
                    placeholder={t('projects.edit.azure.tenant_id_placeholder')}
                    control={control}
                    name={FIELD_NAMES.TENANT_ID}
                    disabled={loading}
                    onChange={getOnChangeSelectField(FIELD_NAMES.TENANT_ID)}
                    options={tenantIds}
                    rules={{ required: t('validation.required') }}
                />
            );

        return null;
    };

    return (
        <SpaceBetween size="l">
            <FormSelect
                label={t('projects.edit.azure.authorization')}
                control={control}
                name={FIELD_NAMES.CREDENTIALS.TYPE}
                onChange={onChangeCredentialsTypeField}
                disabled={loading || availableDefaultCredentials === null}
                secondaryControl={availableDefaultCredentials === null && renderSpinner(true)}
                options={[
                    {
                        label: t('projects.edit.azure.authorization_default'),
                        value: AzureCredentialTypeEnum.DEFAULT,
                        disabled: !availableDefaultCredentials,
                    },
                    {
                        label: t('projects.edit.azure.authorization_client'),
                        value: AzureCredentialTypeEnum.CLIENT,
                    },
                ]}
            />

            {renderTenantIdField()}

            {credentialTypeValue === AzureCredentialTypeEnum.CLIENT && (
                <>
                    <FormInput
                        info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                        label={t('projects.edit.azure.client_id')}
                        description={t('projects.edit.azure.client_id_description')}
                        control={control}
                        name={FIELD_NAMES.CREDENTIALS.CLIENT_ID}
                        onChange={onChangeCredentialField}
                        disabled={loading}
                        rules={{ required: t('validation.required') }}
                        autoComplete="off"
                    />

                    <FormInput
                        info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                        label={t('projects.edit.azure.client_secret')}
                        description={t('projects.edit.azure.client_secret_description')}
                        control={control}
                        name={FIELD_NAMES.CREDENTIALS.CLIENT_SECRET}
                        onChange={onChangeCredentialField}
                        disabled={loading}
                        rules={{ required: t('validation.required') }}
                        autoComplete="off"
                    />
                </>
            )}

            <FormSelect
                info={<InfoLink onFollow={() => openHelpPanel(SUBSCRIPTION_HELP)} />}
                label={t('projects.edit.azure.subscription_id')}
                description={t('projects.edit.azure.subscription_id_description')}
                placeholder={t('projects.edit.azure.subscription_id_placeholder')}
                control={control}
                name={FIELD_NAMES.SUBSCRIPTION_ID}
                disabled={getDisabledByFieldName(FIELD_NAMES.SUBSCRIPTION_ID)}
                onChange={getOnChangeSelectField(FIELD_NAMES.SUBSCRIPTION_ID)}
                options={subscriptionIds}
                rules={{ required: t('validation.required') }}
                secondaryControl={renderSpinner()}
            />

            <FormMultiselect
                info={<InfoLink onFollow={() => openHelpPanel(LOCATIONS_HELP)} />}
                label={t('projects.edit.azure.locations')}
                description={t('projects.edit.azure.locations_description')}
                placeholder={t('projects.edit.azure.locations_placeholder')}
                control={control}
                name={FIELD_NAMES.LOCATIONS}
                onChange={getOnChangeSelectField(FIELD_NAMES.LOCATIONS)}
                disabled={getDisabledByFieldName(FIELD_NAMES.LOCATIONS)}
                secondaryControl={renderSpinner()}
                options={locations}
            />

            <FormSelect
                info={<InfoLink onFollow={() => openHelpPanel(STORAGE_ACCOUNT_HELP)} />}
                label={t('projects.edit.azure.storage_account')}
                description={t('projects.edit.azure.storage_account_description')}
                placeholder={t('projects.edit.azure.storage_account_placeholder')}
                control={control}
                name={FIELD_NAMES.STORAGE_ACCOUNT}
                disabled={getDisabledByFieldName(FIELD_NAMES.STORAGE_ACCOUNT)}
                onChange={getOnChangeSelectField(FIELD_NAMES.STORAGE_ACCOUNT)}
                options={storageAccounts}
                secondaryControl={renderSpinner()}
            />
        </SpaceBetween>
    );
};
