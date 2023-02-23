import React, { useCallback, useEffect, useState } from 'react';
import { IProps } from './types';
import { SpaceBetween, FormInput, FormSelect, FormSelectOptions, FormS3BucketSelector } from 'components';
import { useTranslation } from 'react-i18next';
import { useFormContext } from 'react-hook-form';
import { useBackendValuesMutation } from 'services/hub';
import { debounce } from 'lodash';

export const AWSBackend: React.FC<IProps> = ({ loading: loadingProp }) => {
    const { t } = useTranslation();
    const { control, getValues, setValue } = useFormContext();
    const [regions, setRegions] = useState<FormSelectOptions>([]);
    const [buckets, setBuckets] = useState<TAwsBucket[]>([]);
    const [subnets, setSubnets] = useState<FormSelectOptions>([]);

    const [getBackendValues, { isLoading }] = useBackendValuesMutation();

    useEffect(() => {
        changeFormHandler().catch(console.log);
    }, []);

    const loading = loadingProp || isLoading;

    const changeFormHandler = async () => {
        const backendFormValues = getValues('backend');

        if (!backendFormValues.secret_key || !backendFormValues.access_key) {
            return;
        }

        try {
            const response = await getBackendValues(backendFormValues).unwrap();

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
                setSubnets(response.ec2_subnet_id.values);
            }

            if (response.ec2_subnet_id.selected !== undefined) {
                setValue('backend.ec2_subnet_id', response.ec2_subnet_id.selected);
            }
        } catch (e) {
            console.log('fetch backends values error', e);
        }
    };

    const debouncedChangeFormHandler = useCallback(debounce(changeFormHandler, 1000), []);

    return (
        <SpaceBetween size="l">
            <FormInput
                label={t('hubs.edit.aws.access_key_id')}
                control={control}
                name="backend.access_key"
                onChange={debouncedChangeFormHandler}
                disabled={loading}
            />

            <FormInput
                label={t('hubs.edit.aws.secret_key_id')}
                control={control}
                name="backend.secret_key"
                onChange={debouncedChangeFormHandler}
                disabled={loading}
            />

            <FormSelect
                label={t('hubs.edit.aws.region_name')}
                control={control}
                name="backend.region_name"
                disabled={loading}
                onChange={changeFormHandler}
                options={regions}
            />

            <FormS3BucketSelector
                label={t('hubs.edit.aws.s3_bucket_name')}
                control={control}
                name="backend.s3_bucket_name"
                selectableItemsTypes={['buckets']}
                // onChange={debouncedChangeFormHandler}
                buckets={buckets}
            />

            <FormSelect
                label={t('hubs.edit.aws.ec2_subnet_id')}
                control={control}
                name="backend.ec2_subnet_id"
                disabled={loading}
                onChange={changeFormHandler}
                options={subnets}
            />
        </SpaceBetween>
    );
};
