import React, { useCallback, useEffect, useState, useRef } from 'react';
import { SpaceBetween, FormInput, FormSelect, FormSelectOptions, FormS3BucketSelector, Spinner } from 'components';
import { useTranslation } from 'react-i18next';
import { useFormContext } from 'react-hook-form';
import { debounce } from 'lodash';
import { useBackendValuesMutation } from 'services/hub';
import { IProps } from './types';
import styles from './styles.module.scss';

export const AWSBackend: React.FC<IProps> = ({ loading: loadingProp }) => {
    const { t } = useTranslation();
    const { control, getValues, setValue, setError, clearErrors, watch } = useFormContext();
    const [regions, setRegions] = useState<FormSelectOptions>([]);
    const [buckets, setBuckets] = useState<TAwsBucket[]>([]);
    const [subnets, setSubnets] = useState<FormSelectOptions>([]);

    const [getBackendValues, { data: valuesData, isLoading: isLoadingValues }] = useBackendValuesMutation();

    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);

    useEffect(() => {
        changeFormHandler().catch(console.log);
    }, []);

    const loading = loadingProp;

    const backendAccessKeyValue = watch('backend.access_key');
    const backendSecretKeyValue = watch('backend.secret_key');

    const disabledFields = loading || !backendAccessKeyValue || !backendSecretKeyValue || !valuesData;

    const changeFormHandler = async () => {
        const backendFormValues = getValues('backend');

        if (!backendFormValues.secret_key || !backendFormValues.access_key) {
            return;
        }

        clearErrors('backend.access_key');
        clearErrors('backend.secret_key');

        try {
            const request = getBackendValues(backendFormValues);
            requestRef.current = request;

            const response = await request.unwrap();

            if (response.region_name.values.length) {
                setRegions(response.region_name.values);
            }

            if (response.region_name.selected !== undefined) {
                setValue('backend.region_name', response.region_name.selected);
            }

            if (response.s3_bucket_name.values.length) {
                setBuckets(response.s3_bucket_name.values);
            }

            if (response.s3_bucket_name.selected !== undefined) {
                setValue('backend.s3_bucket_name', response.s3_bucket_name.selected);
            }

            if (response.ec2_subnet_id.values.length) {
                setSubnets([{ value: '', label: 'No preference' }, ...response.ec2_subnet_id.values]);
            }

            if (response.ec2_subnet_id.selected !== undefined) {
                setValue('backend.ec2_subnet_id', response.ec2_subnet_id.selected ?? '');
            }
        } catch (errorResponse) {
            console.log('fetch backends values error:', errorResponse);
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-ignore
            const detailsError = errorResponse?.data?.detail;

            if (detailsError) {
                setError('backend.access_key', { type: 'custom', message: detailsError as string });
                setError('backend.secret_key', { type: 'custom', message: detailsError as string });
            }
        }
    };

    const debouncedChangeFormHandler = useCallback(debounce(changeFormHandler, 1000), []);

    const onChangeCredentialField = () => {
        if (requestRef.current) requestRef.current.abort();
        debouncedChangeFormHandler();
    };

    const onChangeSelectField = () => {
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

    return (
        <SpaceBetween size="l">
            <FormInput
                label={t('projects.edit.aws.access_key_id')}
                control={control}
                name="backend.access_key"
                onChange={onChangeCredentialField}
                disabled={loading}
                rules={{ required: t('validation.required') }}
                autoComplete="off"
            />

            <FormInput
                label={t('projects.edit.aws.secret_key_id')}
                control={control}
                name="backend.secret_key"
                onChange={onChangeCredentialField}
                disabled={loading}
                rules={{ required: t('validation.required') }}
                autoComplete="off"
            />

            <FormSelect
                label={t('projects.edit.aws.region_name')}
                control={control}
                name="backend.region_name"
                disabled={disabledFields}
                onChange={onChangeSelectField}
                options={regions}
                rules={{ required: t('validation.required') }}
                statusType={isLoadingValues ? 'loading' : undefined}
                secondaryControl={renderSpinner()}
            />

            <FormS3BucketSelector
                label={t('projects.edit.aws.s3_bucket_name')}
                control={control}
                name="backend.s3_bucket_name"
                selectableItemsTypes={['buckets']}
                disabled={disabledFields}
                // onChange={debouncedChangeFormHandler}
                buckets={buckets}
                secondaryControl={renderSpinner()}
            />

            <FormSelect
                label={t('projects.edit.aws.ec2_subnet_id')}
                control={control}
                name="backend.ec2_subnet_id"
                disabled={disabledFields}
                onChange={onChangeSelectField}
                options={subnets}
                statusType={isLoadingValues ? 'loading' : undefined}
                secondaryControl={renderSpinner()}
            />
        </SpaceBetween>
    );
};
