import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useFormContext } from 'react-hook-form';
import { IProps } from './types';
import { FormSelect, SpaceBetween, FileUploader, FormSelectOptions, Spinner } from 'components';
import { useBackendValuesMutation } from 'services/project';
import styles from './styles.module.scss';
import { isRequestErrorWithDetail } from '../../../../libs';

export const GCPBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const {
        control,
        setValue,
        getValues,
        setError,
        clearErrors,
        watch,
        formState: { errors },
    } = useFormContext();
    const [files, setFiles] = useState<File[]>([]);
    const [valuesData, setValuesData] = useState<IProjectGCPBackendValues | undefined>();
    const [areaOptions, setAreaOptions] = useState<FormSelectOptions>([]);
    const [regionOptions, setRegionOptions] = useState<FormSelectOptions>([]);
    const [zoneOptions, setZoneOptions] = useState<FormSelectOptions>([]);
    const [bucketNameOptions, setBucketNameOptions] = useState<FormSelectOptions>([]);
    const [subnetOptions, setSubnetOptions] = useState<FormSelectOptions>([]);
    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();
    const backendCredentials = watch('backend.credentials');

    const disabledFields = loading || !backendCredentials || !valuesData;

    useEffect(() => {
        console.log(getValues('backend'));
    });

    const changeFormHandler = async () => {
        const backendFormValues = getValues('backend');

        if (!backendFormValues.credentials) {
            return;
        }

        clearErrors('backend.credentials');

        try {
            const request = getBackendValues(backendFormValues);
            requestRef.current = request;
            const response = await request.unwrap();

            setValuesData(response);

            if (response.area.values.length) {
                setAreaOptions(response.area.values);
            }

            if (response.area.selected !== undefined) {
                setValue('backend.area', response.area.selected);
            }

            if (response.region?.values.length) {
                setRegionOptions(response.region.values);
            }

            if (response.region?.selected !== undefined) {
                setValue('backend.region', response.region.selected);
            }

            if (response.zone?.values.length) {
                setZoneOptions(response.zone.values);
            }

            if (response.zone?.selected !== undefined) {
                setValue('backend.zone', response.zone.selected);
            }

            if (response.bucket_name?.values.length) {
                setBucketNameOptions(response.bucket_name.values);
            }

            if (response.bucket_name?.selected !== undefined) {
                setValue('backend.bucket_name', response.bucket_name.selected);
            }

            if (response.vpc_subnet?.values.length) {
                setSubnetOptions(response.vpc_subnet.values);
            }

            if (response.vpc_subnet?.selected !== undefined) {
                setValue('backend.vpc_subnet', response.vpc_subnet.selected);
            }
        } catch (errorResponse) {
            console.log('fetch backends values error:', errorResponse);
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-ignore
            const errorRequestData = errorResponse?.data;

            if (isRequestErrorWithDetail(errorRequestData)) {
                setError('backend.credentials', { type: 'custom', message: errorRequestData.detail });
            }
        }
    };

    const onChangeFormFields = () => {
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
        <>
            <SpaceBetween size="l">
                <FileUploader
                    fileInputId="gcp-credentials"
                    text="Choose a file to upload"
                    label={t('projects.edit.gcp.credentials')}
                    accept="application/json"
                    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                    // @ts-ignore
                    errorText={errors?.backend?.credentials?.message}
                    files={files}
                    onFilesUploaded={(uploadedFiles) => {
                        if (uploadedFiles.length) {
                            setFiles([...uploadedFiles]);

                            const [file] = uploadedFiles;

                            const reader = new FileReader();
                            reader.onload = function () {
                                const text = reader.result;
                                if (text) {
                                    setValue('backend.credentials', text);
                                    setValue('backend.credentials_filename', file.name);
                                    onChangeFormFields();
                                }
                            };

                            reader.readAsText(file);
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
                    onChange={onChangeFormFields}
                    disabled={disabledFields}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />

                <FormSelect
                    label={t('projects.edit.gcp.region')}
                    description={t('projects.edit.gcp.region_description')}
                    placeholder={t('projects.edit.gcp.region_placeholder')}
                    control={control}
                    name="backend.region"
                    options={regionOptions}
                    onChange={onChangeFormFields}
                    disabled={disabledFields}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />

                <FormSelect
                    label={t('projects.edit.gcp.zone')}
                    description={t('projects.edit.gcp.zone_description')}
                    placeholder={t('projects.edit.gcp.zone_placeholder')}
                    control={control}
                    name="backend.zone"
                    options={zoneOptions}
                    onChange={onChangeFormFields}
                    disabled={disabledFields}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />

                <FormSelect
                    label={t('projects.edit.gcp.bucket_name')}
                    description={t('projects.edit.gcp.bucket_name_description')}
                    placeholder={t('projects.edit.gcp.bucket_name_placeholder')}
                    control={control}
                    name="backend.bucket_name"
                    options={bucketNameOptions}
                    onChange={onChangeFormFields}
                    disabled={disabledFields}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />

                <FormSelect
                    label={t('projects.edit.gcp.subnet')}
                    description={t('projects.edit.gcp.subnet_description')}
                    placeholder={t('projects.edit.gcp.subnet_placeholder')}
                    control={control}
                    name="backend.vpc_subnet"
                    options={subnetOptions}
                    onChange={onChangeFormFields}
                    disabled={disabledFields}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />
            </SpaceBetween>
        </>
    );
};
