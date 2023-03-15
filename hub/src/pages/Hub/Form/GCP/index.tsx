import React from 'react';
import { useTranslation } from 'react-i18next';
import { useFormContext } from 'react-hook-form';
import { IProps } from './types';
import { FormInput, FormSelect, SpaceBetween } from 'components';

export const GCPBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const { control } = useFormContext();

    return (
        <SpaceBetween size="l">
            <FormInput
                label={t('projects.edit.gcp.project')}
                control={control}
                name="backend.project"
                disabled={loading}
                rules={{ required: t('validation.required') }}
            />

            <FormInput
                label={t('projects.edit.gcp.region')}
                control={control}
                name="backend.region"
                disabled={loading}
                rules={{ required: t('validation.required') }}
            />

            <FormInput
                label={t('projects.edit.gcp.zone')}
                control={control}
                name="backend.zone"
                disabled={loading}
                rules={{ required: t('validation.required') }}
            />

            <FormInput
                label={t('projects.edit.gcp.bucket')}
                control={control}
                name="backend.bucket"
                disabled={loading}
                rules={{ required: t('validation.required') }}
            />

            <FormInput
                label={t('projects.edit.gcp.vpc')}
                control={control}
                name="backend.vpc"
                disabled={loading}
                rules={{ required: t('validation.required') }}
            />

            <FormInput
                label={t('projects.edit.gcp.subnet')}
                control={control}
                name="backend.subnet"
                disabled={loading}
                rules={{ required: t('validation.required') }}
            />

            {/*<FormSelect*/}
            {/*    label={t('projects.edit.aws.region_name')}*/}
            {/*    control={control}*/}
            {/*    name="backend.region_name"*/}
            {/*    disabled={loading}*/}
            {/*    onChange={onChangeSelectField}*/}
            {/*    options={regions}*/}
            {/*    rules={{ required: t('validation.required') }}*/}
            {/*    statusType={isLoadingValues ? 'loading' : undefined}*/}
            {/*    secondaryControl={renderSpinner()}*/}
            {/*/>*/}
        </SpaceBetween>
    );
};
