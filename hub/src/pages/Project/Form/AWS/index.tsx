import React, { useCallback, useEffect, useState, useRef } from 'react';
import { SpaceBetween, FormInput, FormSelect, FormSelectOptions, FormS3BucketSelector, Spinner } from 'components';
import { useTranslation } from 'react-i18next';
import { useFormContext } from 'react-hook-form';
import { debounce } from 'lodash';
import { useBackendValuesMutation } from 'services/project';
import { IProps } from './types';
import { isRequestFormFieldError, isRequestFormErrors2 } from 'libs';
import { useNotifications } from 'hooks';
import { FIELD_NAMES } from './constants';
import styles from './styles.module.scss';

export const AWSBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const { control, getValues, setValue, setError, clearErrors, watch } = useFormContext();
    const [valuesData, setValuesData] = useState<IProjectAwsBackendValues | undefined>();
    const [regions, setRegions] = useState<FormSelectOptions>([]);
    const [buckets, setBuckets] = useState<TAwsBucket[]>([]);
    const [subnets, setSubnets] = useState<FormSelectOptions>([]);
    const lastUpdatedField = useRef<string | null>(null);

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();

    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);

    useEffect(() => {
        changeFormHandler().catch(console.log);
    }, []);

    const backendAccessKeyValue = watch(`backend.${FIELD_NAMES.ACCESS_KEY}`);
    const backendSecretKeyValue = watch(`backend.${FIELD_NAMES.SECRET_KEY}`);

    const changeFormHandler = async () => {
        const backendFormValues = getValues('backend');

        if (!backendFormValues.secret_key || !backendFormValues.access_key) {
            return;
        }

        clearErrors('backend');

        try {
            const request = getBackendValues(backendFormValues);
            requestRef.current = request;

            const response = await request.unwrap();

            setValuesData(response);

            lastUpdatedField.current = null;

            if (response.region_name.values) {
                setRegions(response.region_name.values);
            }

            if (response.region_name.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.REGION_NAME}`, response.region_name.selected);
            }

            if (response.s3_bucket_name.values) {
                setBuckets(response.s3_bucket_name.values);
            }

            if (response.s3_bucket_name.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.S3_BUCKET_NAME}`, response.s3_bucket_name.selected);
            }

            if (response.ec2_subnet_id.values) {
                setSubnets([{ value: '', label: 'No preference' }, ...response.ec2_subnet_id.values]);
            }

            if (response.ec2_subnet_id.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.EC2_SUBNET_ID}`, response.ec2_subnet_id.selected ?? '');
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
        if (requestRef.current) requestRef.current.abort();
        debouncedChangeFormHandler();
    };

    const getOnChangeSelectField = (fieldName: string) => () => {
        lastUpdatedField.current = fieldName;
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
        let disabledField = loading || !backendAccessKeyValue || !backendSecretKeyValue || !valuesData;

        disabledField = disabledField || (lastUpdatedField.current !== fieldName && isLoadingValues);

        return disabledField;
    };

    return (
        <SpaceBetween size="l">
            <FormInput
                label={t('projects.edit.aws.access_key_id')}
                description={t('projects.edit.aws.access_key_id_description')}
                control={control}
                name={`backend.${FIELD_NAMES.ACCESS_KEY}`}
                onChange={onChangeCredentialField}
                disabled={loading}
                rules={{ required: t('validation.required') }}
                autoComplete="off"
            />

            <FormInput
                label={t('projects.edit.aws.secret_key_id')}
                description={t('projects.edit.aws.secret_key_id_description')}
                control={control}
                name={`backend.${FIELD_NAMES.SECRET_KEY}`}
                onChange={onChangeCredentialField}
                disabled={loading}
                rules={{ required: t('validation.required') }}
                autoComplete="off"
            />

            <FormSelect
                label={t('projects.edit.aws.region_name')}
                description={t('projects.edit.aws.region_name_description')}
                placeholder={t('projects.edit.aws.region_name_placeholder')}
                control={control}
                name={`backend.${FIELD_NAMES.REGION_NAME}`}
                disabled={getDisabledByFieldName(FIELD_NAMES.REGION_NAME)}
                onChange={getOnChangeSelectField(FIELD_NAMES.REGION_NAME)}
                options={regions}
                rules={{ required: t('validation.required') }}
                secondaryControl={renderSpinner()}
            />

            <FormS3BucketSelector
                label={t('projects.edit.aws.s3_bucket_name')}
                description={t('projects.edit.aws.s3_bucket_name_description')}
                control={control}
                name={`backend.${FIELD_NAMES.S3_BUCKET_NAME}`}
                selectableItemsTypes={['buckets']}
                disabled={getDisabledByFieldName(FIELD_NAMES.S3_BUCKET_NAME)}
                rules={{ required: t('validation.required') }}
                buckets={buckets}
                secondaryControl={renderSpinner()}
                i18nStrings={{
                    inContextBrowseButton: 'Browse buckets',
                    modalBreadcrumbRootItem: 'S3 buckets',
                    modalTitle: 'Choose an S3 bucket',
                }}
            />

            <FormSelect
                label={t('projects.edit.aws.ec2_subnet_id')}
                description={t('projects.edit.aws.ec2_subnet_id_description')}
                placeholder={t('projects.edit.aws.ec2_subnet_id_placeholder')}
                control={control}
                name="backend.ec2_subnet_id"
                disabled={getDisabledByFieldName(FIELD_NAMES.EC2_SUBNET_ID)}
                onChange={getOnChangeSelectField(FIELD_NAMES.EC2_SUBNET_ID)}
                options={subnets}
                secondaryControl={renderSpinner()}
            />
        </SpaceBetween>
    );
};
