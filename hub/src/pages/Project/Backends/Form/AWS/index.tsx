import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { debounce } from 'lodash';

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
import { AWSCredentialTypeEnum } from 'types';

import { ADDITIONAL_REGIONS_HELP, BUCKET_HELP, CREDENTIALS_HELP, FIELD_NAMES, REGION_HELP, SUBNET_HELP } from './constants';

import { IProps } from './types';

import styles from './styles.module.scss';

export const AWSBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const { control, getValues, setValue, setError, clearErrors, watch } = useFormContext();
    const [valuesData, setValuesData] = useState<IAwsBackendValues | undefined>();
    const [regions, setRegions] = useState<FormSelectOptions>([]);
    const [buckets, setBuckets] = useState<TAwsBucket[]>([]);
    const [subnets, setSubnets] = useState<FormSelectOptions>([]);
    const [extraRegions, setExtraRegions] = useState<FormMultiselectOptions>([]);
    const [availableDefaultCredentials, setAvailableDefaultCredentials] = useState<null | boolean>(null);
    const lastUpdatedField = useRef<string | null>(null);
    const isFirstRender = useRef<boolean>(true);
    const isMounted = useIsMounted();

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();

    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);

    const [openHelpPanel] = useHelpPanel();

    const credentialTypeValue = watch(FIELD_NAMES.CREDENTIALS.TYPE);
    const accessKeyValue = watch(FIELD_NAMES.CREDENTIALS.ACCESS_KEY);
    const secretKeyValue = watch(FIELD_NAMES.CREDENTIALS.SECRET_KEY);

    const changeFormHandler = async () => {
        let formValues = getValues();

        if (
            formValues.credentials?.type === AWSCredentialTypeEnum.ACCESS_KEY &&
            (!formValues.credentials?.secret_key || !formValues.credentials?.access_key)
        ) {
            return;
        }

        if (!formValues.credentials?.type) {
            const { credentials, ...otherValues } = formValues;

            formValues = otherValues;
        }

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
            if (!formValues?.credentials?.type) {
                setValue(
                    FIELD_NAMES.CREDENTIALS.TYPE,
                    response.default_credentials ? AWSCredentialTypeEnum.DEFAULT : AWSCredentialTypeEnum.ACCESS_KEY,
                );

                if (response.default_credentials) changeFormHandler().catch(console.log);
            }

            if (response.region_name?.values) {
                setRegions(response.region_name.values);
            }

            if (response.region_name?.selected !== undefined) {
                setValue(FIELD_NAMES.REGION_NAME, response.region_name.selected);
            }

            if (response.s3_bucket_name?.values) {
                setBuckets(response.s3_bucket_name.values);
            }

            if (response.s3_bucket_name?.selected !== undefined) {
                setValue(FIELD_NAMES.S3_BUCKET_NAME, response.s3_bucket_name.selected);
            }

            if (response.ec2_subnet_id?.values) {
                setSubnets([{ value: '', label: 'No preference' }, ...response.ec2_subnet_id.values]);
            }

            if (response.ec2_subnet_id?.selected !== undefined) {
                setValue(FIELD_NAMES.EC2_SUBNET_ID, response.ec2_subnet_id.selected ?? '');
            }

            if (response.extra_regions?.values) {
                setExtraRegions(response.extra_regions.values);
            }

            if (response.extra_regions?.selected !== undefined) {
                setValue(FIELD_NAMES.EXTRA_REGIONS, response.extra_regions.selected);
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
        if (requestRef.current) requestRef.current.abort();
        debouncedChangeFormHandler();
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
        let disabledField = loading || !credentialTypeValue || !valuesData;

        disabledField =
            disabledField || (credentialTypeValue === AWSCredentialTypeEnum.ACCESS_KEY && (!accessKeyValue || !secretKeyValue));

        disabledField = disabledField || (lastUpdatedField.current !== fieldName && isLoadingValues);

        return disabledField;
    };

    return (
        <SpaceBetween size="l">
            <FormSelect
                label={t('projects.edit.aws.authorization')}
                control={control}
                name={FIELD_NAMES.CREDENTIALS.TYPE}
                onChange={getOnChangeSelectField(FIELD_NAMES.CREDENTIALS.TYPE)}
                disabled={loading || availableDefaultCredentials === null}
                secondaryControl={availableDefaultCredentials === null && renderSpinner(true)}
                options={[
                    {
                        label: t('projects.edit.aws.authorization_default'),
                        value: AWSCredentialTypeEnum.DEFAULT,
                        disabled: !availableDefaultCredentials,
                    },
                    {
                        label: t('projects.edit.aws.authorization_access_key'),
                        value: AWSCredentialTypeEnum.ACCESS_KEY,
                    },
                ]}
            />

            {credentialTypeValue === AWSCredentialTypeEnum.ACCESS_KEY && (
                <>
                    <FormInput
                        info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                        label={t('projects.edit.aws.access_key_id')}
                        description={t('projects.edit.aws.access_key_id_description')}
                        control={control}
                        name={FIELD_NAMES.CREDENTIALS.ACCESS_KEY}
                        onChange={onChangeCredentialField}
                        disabled={loading}
                        rules={{ required: t('validation.required') }}
                        autoComplete="off"
                    />

                    <FormInput
                        info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                        label={t('projects.edit.aws.secret_key_id')}
                        description={t('projects.edit.aws.secret_key_id_description')}
                        control={control}
                        name={FIELD_NAMES.CREDENTIALS.SECRET_KEY}
                        onChange={onChangeCredentialField}
                        disabled={loading}
                        rules={{ required: t('validation.required') }}
                        autoComplete="off"
                    />
                </>
            )}

            <FormSelect
                info={<InfoLink onFollow={() => openHelpPanel(REGION_HELP)} />}
                label={t('projects.edit.aws.region_name')}
                description={t('projects.edit.aws.region_name_description')}
                placeholder={t('projects.edit.aws.region_name_placeholder')}
                control={control}
                name={FIELD_NAMES.REGION_NAME}
                disabled={getDisabledByFieldName(FIELD_NAMES.REGION_NAME)}
                onChange={getOnChangeSelectField(FIELD_NAMES.REGION_NAME)}
                options={regions}
                rules={{ required: t('validation.required') }}
                secondaryControl={renderSpinner()}
            />

            <FormS3BucketSelector
                info={<InfoLink onFollow={() => openHelpPanel(BUCKET_HELP)} />}
                label={t('projects.edit.aws.s3_bucket_name')}
                description={t('projects.edit.aws.s3_bucket_name_description')}
                control={control}
                name={FIELD_NAMES.S3_BUCKET_NAME}
                selectableItemsTypes={['buckets']}
                disabled={getDisabledByFieldName(FIELD_NAMES.S3_BUCKET_NAME)}
                rules={{ required: t('validation.required') }}
                buckets={buckets}
                secondaryControl={renderSpinner()}
                i18nStrings={{
                    inContextBrowseButton: 'Choose a bucket',
                    modalBreadcrumbRootItem: 'S3 buckets',
                    modalTitle: 'Choose an S3 bucket',
                }}
            />

            <FormSelect
                info={<InfoLink onFollow={() => openHelpPanel(SUBNET_HELP)} />}
                label={t('projects.edit.aws.ec2_subnet_id')}
                description={t('projects.edit.aws.ec2_subnet_id_description')}
                placeholder={t('projects.edit.aws.ec2_subnet_id_placeholder')}
                control={control}
                name={FIELD_NAMES.EC2_SUBNET_ID}
                disabled={getDisabledByFieldName(FIELD_NAMES.EC2_SUBNET_ID)}
                onChange={getOnChangeSelectField(FIELD_NAMES.EC2_SUBNET_ID)}
                options={subnets}
                secondaryControl={renderSpinner()}
            />

            <FormMultiselect
                info={<InfoLink onFollow={() => openHelpPanel(ADDITIONAL_REGIONS_HELP)} />}
                label={t('projects.edit.aws.extra_regions')}
                description={t('projects.edit.aws.extra_regions_description')}
                placeholder={t('projects.edit.aws.extra_regions_placeholder')}
                control={control}
                name={FIELD_NAMES.EXTRA_REGIONS}
                onChange={getOnChangeSelectField(FIELD_NAMES.EXTRA_REGIONS)}
                disabled={getDisabledByFieldName(FIELD_NAMES.EXTRA_REGIONS)}
                secondaryControl={renderSpinner()}
                options={extraRegions}
            />
        </SpaceBetween>
    );
};
