import React, { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useFormContext } from 'react-hook-form';
import { IProps } from './types';
import { FormSelect, SpaceBetween, FileUploader, FormSelectOptions } from 'components';
import { useBackendValuesMutation } from 'services/project';

export const GCPBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const { control, register, setValue, getValues } = useFormContext();
    const [files, setFiles] = useState<File[]>([]);
    const [areaOptions, setAreaOptions] = useState<FormSelectOptions>([]);
    const [regionOptions, setRegionOptions] = useState<FormSelectOptions>([]);
    const [zoneOptions, setZoneOptions] = useState<FormSelectOptions>([]);
    const [bucketNameOptions, setBucketNameOptions] = useState<FormSelectOptions>([]);
    const [vpcOptions, setVpcOptions] = useState<FormSelectOptions>([]);
    const [subnetOptions, setSubnetOptions] = useState<FormSelectOptions>([]);
    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();

    const changeFormHandler = async () => {
        const backendFormValues = getValues('backend');

        console.log(backendFormValues);

        if (!backendFormValues.credentials) {
            return;
        }

        try {
            const request = getBackendValues(backendFormValues);
            requestRef.current = request;
            const response = await request.unwrap();
            console.log(response);
        } catch (errorResponse) {
            console.log('fetch backends values error:', errorResponse);
        }
    };

    const onChangeFormFields = () => {
        if (requestRef.current) requestRef.current.abort();
        changeFormHandler().catch(console.log);
    };

    return (
        <>
            <input type="hidden" {...register('backend.credentials')} />

            <SpaceBetween size="l">
                <FileUploader
                    fileInputId="gcp-credentials"
                    text="Choose a file to upload"
                    label={t('projects.edit.gcp.credentials')}
                    accept="application/json"
                    // errorText={errorText}
                    files={files}
                    onFilesUploaded={(uploadedFiles) => {
                        if (uploadedFiles.length) {
                            setFiles([...uploadedFiles]);

                            const reader = new FileReader();
                            reader.onload = function () {
                                const text = reader.result;
                                if (text) {
                                    setValue('backend.credentials', text);
                                    onChangeFormFields();
                                }
                            };

                            reader.readAsText(uploadedFiles[0]);
                        }
                    }}
                />

                <FormSelect
                    label={t('projects.edit.gcp.area')}
                    description={t('projects.edit.gcp.area_description')}
                    placeholder={t('projects.edit.gcp.area_placeholder')}
                    control={control}
                    name="backend.area"
                    options={areaOptions}
                    rules={{ required: t('validation.required') }}
                />

                <FormSelect
                    label={t('projects.edit.gcp.region')}
                    description={t('projects.edit.gcp.region_description')}
                    placeholder={t('projects.edit.gcp.region_placeholder')}
                    control={control}
                    name="backend.region"
                    options={regionOptions}
                    rules={{ required: t('validation.required') }}
                />

                <FormSelect
                    label={t('projects.edit.gcp.zone')}
                    description={t('projects.edit.gcp.zone_description')}
                    placeholder={t('projects.edit.gcp.zone_placeholder')}
                    control={control}
                    name="backend.zone"
                    options={zoneOptions}
                    rules={{ required: t('validation.required') }}
                />

                <FormSelect
                    label={t('projects.edit.gcp.bucket_name')}
                    description={t('projects.edit.gcp.bucket_name_description')}
                    placeholder={t('projects.edit.gcp.bucket_name_placeholder')}
                    control={control}
                    name="backend.bucket_name"
                    options={bucketNameOptions}
                    rules={{ required: t('validation.required') }}
                />

                <FormSelect
                    label={t('projects.edit.gcp.vpc')}
                    description={t('projects.edit.gcp.vpc_description')}
                    placeholder={t('projects.edit.gcp.vpc_placeholder')}
                    control={control}
                    name="backend.vpc"
                    options={vpcOptions}
                    rules={{ required: t('validation.required') }}
                />

                <FormSelect
                    label={t('projects.edit.gcp.subnet')}
                    description={t('projects.edit.gcp.subnet_description')}
                    placeholder={t('projects.edit.gcp.subnet_placeholder')}
                    control={control}
                    name="backend.subnet"
                    options={subnetOptions}
                    rules={{ required: t('validation.required') }}
                />
            </SpaceBetween>
        </>
    );
};
