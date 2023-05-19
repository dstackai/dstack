import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { debounce } from 'lodash';

import { FormInput, FormSelect, FormSelectOptions, InfoLink, SpaceBetween, Spinner } from 'components';

import { useHelpPanel, useNotifications } from 'hooks';
import { isRequestFormErrors2, isRequestFormFieldError } from 'libs';
import { useBackendValuesMutation } from 'services/project';

import { CREDENTIALS_HELP, FIELD_NAMES, LOCATION_HELP, STORAGE_ACCOUNT_HELP, SUBSCRIPTION_HELP } from './constants';

import { IProps } from './types';

import styles from './styles.module.scss';

const CREDS_FIELDS = [
    FIELD_NAMES.TENANT_ID,
    FIELD_NAMES.CLIENT_ID,
    FIELD_NAMES.CLIENT_SECRET,
]
const FIELDS_QUEUE = [
    FIELD_NAMES.SUBSCRIPTION_ID,
    FIELD_NAMES.LOCATION,
    FIELD_NAMES.STORAGE_ACCOUNT,
];

export const AzureBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const { control, getValues, setValue, setError, clearErrors, watch } = useFormContext();
    const [valuesData, setValuesData] = useState<IProjectAzureBackendValues | undefined>();
    const [subscriptionIds, setSubscriptionIds] = useState<FormSelectOptions>([]);
    const [locations, setLocations] = useState<FormSelectOptions>([]);
    const [storageAccounts, setStorageAccounts] = useState<FormSelectOptions>([]);
    const lastUpdatedField = useRef<string | null>(null);

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();

    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);

    const [openHelpPanel] = useHelpPanel();

    useEffect(() => {
        changeFormHandler().catch(console.log);
    }, []);

    const tenantIdValue = watch(`backend.${FIELD_NAMES.TENANT_ID}`);
    const clientIdValue = watch(`backend.${FIELD_NAMES.CLIENT_ID}`);
    const clientSecretValue = watch(`backend.${FIELD_NAMES.CLIENT_SECRET}`);

    const changeFormHandler = async () => {
        const backendFormValues = getValues('backend');

        if (!backendFormValues.client_secret || !backendFormValues.client_id || !backendFormValues.tenant_id) {
            return;
        }

        clearErrors('backend');

        try {
            const request = getBackendValues(backendFormValues);
            requestRef.current = request;
            const response = await request.unwrap();
            setValuesData(response);
            lastUpdatedField.current = null;

            if (response.subscription_id.values) {
                setSubscriptionIds(response.subscription_id.values);
            }
            if (response.subscription_id.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.SUBSCRIPTION_ID}`, response.subscription_id.selected);
            }
            if (response.location.values) {
                setLocations(response.location.values);
            }
            if (response.location.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.LOCATION}`, response.location.selected);
            }
            if (response.storage_account.values) {
                setStorageAccounts(response.storage_account.values);
            }
            if (response.storage_account.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.STORAGE_ACCOUNT}`, response.storage_account.selected);
            }
        } catch (errorResponse) {
            console.log('fetch backends values error:', errorResponse);
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-ignore
            const errorRequestData = errorResponse?.data;

            if (isRequestFormErrors2(errorRequestData)) {
                errorRequestData.detail.forEach((error) => {
                    if (isRequestFormFieldError(error)) {
                        setError(`backend.${error.loc.join('.')}`, { type: 'custom', message: error.msg });
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

    const debouncedChangeFormHandler = useCallback(debounce(changeFormHandler, 1000), []);

    const onChangeCredentialField = () => {
        clearFields(0)
        if (requestRef.current) requestRef.current.abort();
        debouncedChangeFormHandler();
    };

    const clearFieldByQueueFromField = (name: string) => {
        let fieldIndex = FIELDS_QUEUE.findIndex((i) => i === name);
        if (fieldIndex < 0) return;
        clearFields(fieldIndex + 1)
    };

    const clearFields = (startIndex: number) => {
        for (let i = startIndex; i < FIELDS_QUEUE.length; i++) {
            setValue(`backend.${FIELDS_QUEUE[i]}`, null);
        }
    };

    const getOnChangeSelectField = (fieldName: string) => () => {
        lastUpdatedField.current = fieldName;
        clearFieldByQueueFromField(fieldName);
        if (requestRef.current) requestRef.current.abort();
        changeFormHandler().catch(console.log);
    };

    const renderSpinner = () => {
        if (isLoadingValues)
            return (
                <div className={styles.fieldSpinner}>
                    <Spinner />
                </div>
            );
    };

    const getDisabledByFieldName = (fieldName: string) => {
        let disabledField = loading || !tenantIdValue || !clientIdValue || !clientSecretValue || !valuesData;
        disabledField = disabledField || (lastUpdatedField.current !== fieldName && isLoadingValues);

        switch (fieldName) {
            case FIELD_NAMES.SUBSCRIPTION_ID:
                disabledField = disabledField || !subscriptionIds.length;
                break;
            case FIELD_NAMES.LOCATION:
                disabledField = disabledField || !locations.length;
                break;
            case FIELD_NAMES.STORAGE_ACCOUNT:
                disabledField = disabledField || !getValues('backend').location;
                break;
        }

        return disabledField;
    };

    return (
        <SpaceBetween size="l">
            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                label={t('projects.edit.azure.tenant_id')}
                description={t('projects.edit.azure.tenant_id_description')}
                control={control}
                name={`backend.${FIELD_NAMES.TENANT_ID}`}
                onChange={onChangeCredentialField}
                disabled={loading}
                rules={{ required: t('validation.required') }}
            />

            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                label={t('projects.edit.azure.client_id')}
                description={t('projects.edit.azure.client_id_description')}
                control={control}
                name={`backend.${FIELD_NAMES.CLIENT_ID}`}
                onChange={onChangeCredentialField}
                disabled={loading}
                rules={{ required: t('validation.required') }}
                // autoComplete="off"
            />

            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                label={t('projects.edit.azure.client_secret')}
                description={t('projects.edit.azure.client_secret_description')}
                control={control}
                name={`backend.${FIELD_NAMES.CLIENT_SECRET}`}
                onChange={onChangeCredentialField}
                disabled={loading}
                rules={{ required: t('validation.required') }}
                // autoComplete="off"
            />

            <FormSelect
                info={<InfoLink onFollow={() => openHelpPanel(SUBSCRIPTION_HELP)} />}
                label={t('projects.edit.azure.subscription_id')}
                description={t('projects.edit.azure.subscription_id_description')}
                placeholder={t('projects.edit.azure.subscription_id_placeholder')}
                control={control}
                name={`backend.${FIELD_NAMES.SUBSCRIPTION_ID}`}
                disabled={getDisabledByFieldName(FIELD_NAMES.SUBSCRIPTION_ID)}
                onChange={getOnChangeSelectField(FIELD_NAMES.SUBSCRIPTION_ID)}
                options={subscriptionIds}
                rules={{ required: t('validation.required') }}
                secondaryControl={renderSpinner()}
            />

            <FormSelect
                info={<InfoLink onFollow={() => openHelpPanel(LOCATION_HELP)} />}
                label={t('projects.edit.azure.location')}
                description={t('projects.edit.azure.location_description')}
                placeholder={t('projects.edit.azure.location_placeholder')}
                control={control}
                name={`backend.${FIELD_NAMES.LOCATION}`}
                disabled={getDisabledByFieldName(FIELD_NAMES.LOCATION)}
                onChange={getOnChangeSelectField(FIELD_NAMES.LOCATION)}
                options={locations}
                rules={{ required: t('validation.required') }}
                secondaryControl={renderSpinner()}
            />

            <FormSelect
                info={<InfoLink onFollow={() => openHelpPanel(STORAGE_ACCOUNT_HELP)} />}
                label={t('projects.edit.azure.storage_account')}
                description={t('projects.edit.azure.storage_account_description')}
                placeholder={t('projects.edit.azure.storage_account_placeholder')}
                control={control}
                name={`backend.${FIELD_NAMES.STORAGE_ACCOUNT}`}
                disabled={getDisabledByFieldName(FIELD_NAMES.STORAGE_ACCOUNT)}
                onChange={getOnChangeSelectField(FIELD_NAMES.STORAGE_ACCOUNT)}
                options={storageAccounts}
                secondaryControl={renderSpinner()}
            />
        </SpaceBetween>
    );
};
