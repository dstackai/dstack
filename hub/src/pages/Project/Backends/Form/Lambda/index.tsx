import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { debounce, get as _get } from 'lodash';

import {
    FormInput,
    FormMultiselect,
    FormMultiselectOptions,
    FormS3BucketSelector,
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

import { API_KEY_HELP, BUCKET_HELP, CREDENTIALS_HELP, FIELD_NAMES, REGIONS_HELP, STORAGE_HELP } from './constants';

import { IProps } from './types';

import styles from '../AWS/styles.module.scss';

export const LambdaBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const { control, getValues, setValue, setError, clearErrors } = useFormContext();
    const [valuesData, setValuesData] = useState<IAwsBackendValues | undefined>();
    const [regions, setRegions] = useState<FormMultiselectOptions>([]);
    const [buckets, setBuckets] = useState<TAwsBucket[]>([]);
    const [storageBackendType, setStorageBackendType] = useState<FormSelectOptions>([]);
    const lastUpdatedField = useRef<string | null>(null);
    const isFirstRender = useRef<boolean>(true);
    const isMounted = useIsMounted();

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();

    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);

    const [openHelpPanel] = useHelpPanel();

    const changeFormHandler = async () => {
        const formValues = getValues();

        if (!formValues.api_key) {
            return;
        }

        if (
            formValues?.storage_backend?.credentials &&
            !_get(formValues, FIELD_NAMES.STORAGE_BACKEND.CREDENTIALS.ACCESS_KEY) &&
            !_get(formValues, FIELD_NAMES.STORAGE_BACKEND.CREDENTIALS.SECRET_KEY)
        )
            formValues.storage_backend.credentials = null;

        clearErrors();

        try {
            const request = getBackendValues(formValues);
            requestRef.current = request;

            const response = await request.unwrap();

            if (!isMounted()) return;

            setValuesData(response);

            lastUpdatedField.current = null;

            if (response.regions?.values) {
                setRegions(response.regions.values);
            }

            if (response.regions?.selected !== undefined) {
                setValue(FIELD_NAMES.REGIONS, response.regions.selected);
            }

            if (response.storage_backend_type?.values) {
                setStorageBackendType(response.storage_backend_type.values);
            }

            if (response.storage_backend_type?.selected !== undefined) {
                setValue(FIELD_NAMES.STORAGE_BACKEND.TYPE, response.storage_backend_type.selected);
            }

            if (response.storage_backend_values?.bucket_name?.values) {
                const formattedBuckets = response.storage_backend_values.bucket_name.values.map(({ value }) => ({
                    name: value,
                }));

                setBuckets(formattedBuckets);
            }

            if (response.storage_backend_values?.bucket_name?.selected !== undefined) {
                setValue(FIELD_NAMES.STORAGE_BACKEND.BUCKET_NAME, response.storage_backend_values.bucket_name.selected);
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

    const getOnChangeSelectField = (fieldName: string) => () => {
        lastUpdatedField.current = fieldName;
        if (requestRef.current) requestRef.current.abort();
        changeFormHandler().catch(console.log);
    };
    const onChangeCredentialField = () => {
        if (requestRef.current) requestRef.current.abort();
        debouncedChangeFormHandler();
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
        let disabledField = loading || !valuesData;

        disabledField = disabledField || (lastUpdatedField.current !== fieldName && isLoadingValues);

        return disabledField;
    };

    return (
        <SpaceBetween size="l">
            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(API_KEY_HELP)} />}
                label={t('projects.edit.lambda.api_key')}
                description={t('projects.edit.lambda.api_key_description')}
                control={control}
                name={FIELD_NAMES.API_KEY}
                onChange={onChangeCredentialField}
                disabled={loading}
                rules={{ required: t('validation.required') }}
                autoComplete="off"
            />

            <FormMultiselect
                info={<InfoLink onFollow={() => openHelpPanel(REGIONS_HELP)} />}
                label={t('projects.edit.lambda.regions')}
                description={t('projects.edit.lambda.regions_description')}
                placeholder={t('projects.edit.lambda.regions_placeholder')}
                control={control}
                name={FIELD_NAMES.REGIONS}
                onChange={getOnChangeSelectField(FIELD_NAMES.REGIONS)}
                disabled={getDisabledByFieldName(FIELD_NAMES.REGIONS)}
                secondaryControl={renderSpinner()}
                rules={{ required: t('validation.required') }}
                options={regions}
            />

            <FormSelect
                info={<InfoLink onFollow={() => openHelpPanel(STORAGE_HELP)} />}
                label={t('projects.edit.lambda.storage_backend.type')}
                description={t('projects.edit.lambda.storage_backend.type_description')}
                placeholder={t('projects.edit.lambda.storage_backend.type_placeholder')}
                control={control}
                name={FIELD_NAMES.STORAGE_BACKEND.TYPE}
                disabled={getDisabledByFieldName(FIELD_NAMES.STORAGE_BACKEND.TYPE)}
                onChange={getOnChangeSelectField(FIELD_NAMES.STORAGE_BACKEND.TYPE)}
                options={storageBackendType}
                rules={{ required: t('validation.required') }}
                secondaryControl={renderSpinner()}
            />

            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                label={t('projects.edit.lambda.storage_backend.credentials.access_key_id')}
                description={t('projects.edit.lambda.storage_backend.credentials.access_key_id_description')}
                control={control}
                name={FIELD_NAMES.STORAGE_BACKEND.CREDENTIALS.ACCESS_KEY}
                onChange={onChangeCredentialField}
                rules={{ required: t('validation.required') }}
                disabled={getDisabledByFieldName(FIELD_NAMES.STORAGE_BACKEND.CREDENTIALS.ACCESS_KEY)}
                autoComplete="off"
            />

            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                label={t('projects.edit.lambda.storage_backend.credentials.secret_key_id')}
                description={t('projects.edit.lambda.storage_backend.credentials.secret_key_id_description')}
                control={control}
                name={FIELD_NAMES.STORAGE_BACKEND.CREDENTIALS.SECRET_KEY}
                onChange={onChangeCredentialField}
                rules={{ required: t('validation.required') }}
                disabled={getDisabledByFieldName(FIELD_NAMES.STORAGE_BACKEND.CREDENTIALS.SECRET_KEY)}
                autoComplete="off"
            />

            <FormS3BucketSelector
                info={<InfoLink onFollow={() => openHelpPanel(BUCKET_HELP)} />}
                label={t('projects.edit.lambda.storage_backend.s3_bucket_name')}
                description={t('projects.edit.lambda.storage_backend.s3_bucket_name_description')}
                control={control}
                name={FIELD_NAMES.STORAGE_BACKEND.BUCKET_NAME}
                selectableItemsTypes={['buckets']}
                disabled={getDisabledByFieldName(FIELD_NAMES.STORAGE_BACKEND.BUCKET_NAME)}
                rules={{ required: t('validation.required') }}
                buckets={buckets}
                secondaryControl={renderSpinner()}
                i18nStrings={{
                    inContextBrowseButton: 'Choose a bucket',
                    modalBreadcrumbRootItem: 'S3 buckets',
                    modalTitle: 'Choose an S3 bucket',
                }}
            />
        </SpaceBetween>
    );
};
