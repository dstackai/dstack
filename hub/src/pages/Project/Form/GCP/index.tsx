import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useFormContext } from 'react-hook-form';
import { IProps, VPCSubnetOption } from './types';
import { FormSelect, SpaceBetween, FileUploader, FormSelectOptions, Spinner } from 'components';
import { useBackendValuesMutation } from 'services/project';
import { isRequestFormFieldError, isRequestFormErrors2 } from 'libs';
import { useNotifications } from 'hooks';
import styles from './styles.module.scss';
import { FIELD_NAMES } from './constants';

const FIELDS_QUEUE = [
    FIELD_NAMES.CREDENTIALS,
    FIELD_NAMES.AREA,
    FIELD_NAMES.REGION,
    FIELD_NAMES.ZONE,
    FIELD_NAMES.BUCKET_NAME,
    FIELD_NAMES.VPC_SUBNET,
    FIELD_NAMES.VPC,
    FIELD_NAMES.SUBNET,
];
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
    const [subnetOptions, setSubnetOptions] = useState<VPCSubnetOption[]>([]);
    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);
    const [pushNotification] = useNotifications();

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();
    const backendCredentials = watch('backend.credentials');

    const disabledFields = loading || !backendCredentials || !valuesData;

    useEffect(() => {
        changeFormHandler().catch(console.log);

        const fileName = getValues('backend.credentials_filename');

        if (fileName) {
            const file = new File([''], fileName, { type: 'text/plain' });
            setFiles([file]);
        }
    }, []);

    const changeFormHandler = async () => {
        const backendFormValues = getValues('backend');

        if (!backendFormValues.credentials) {
            return;
        }

        clearErrors(`backend.${FIELD_NAMES.CREDENTIALS}`);

        try {
            const request = getBackendValues(backendFormValues);
            requestRef.current = request;
            const response = await request.unwrap();

            setValuesData(response);

            if (response.area.values.length) {
                setAreaOptions(response.area.values);
            }

            if (response.area.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.AREA}`, response.area.selected);
            }

            if (response.region?.values.length) {
                setRegionOptions(response.region.values);
            }

            if (response.region?.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.REGION}`, response.region.selected);
            }

            if (response.zone?.values.length) {
                setZoneOptions(response.zone.values);
            }

            if (response.zone?.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.ZONE}`, response.zone.selected);
            }

            if (response.bucket_name?.values.length) {
                setBucketNameOptions(response.bucket_name.values);
            }

            if (response.bucket_name?.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.BUCKET_NAME}`, response.bucket_name.selected);
            }

            if (response.vpc_subnet?.values.length) {
                // it needs for working form, because options from api doesn't have value property
                const vpcSubnetOptions: VPCSubnetOption[] = response.vpc_subnet.values.map((i) => ({
                    ...i,
                    value: i.label,
                }));

                setSubnetOptions(vpcSubnetOptions);
            }

            if (response.vpc_subnet?.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.VPC_SUBNET}`, response.vpc_subnet.selected);

                const valueItem = response.vpc_subnet.values.find((i) => i.label === response.vpc_subnet?.selected);

                if (!valueItem) return;

                setVPCSubnetFormValue({
                    vpc: valueItem.vpc,
                    subnet: valueItem.subnet,
                });
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

    const onChangeFormField = () => {
        if (requestRef.current) requestRef.current.abort();
        changeFormHandler().catch(console.log);
    };

    const clearFieldByQueueFromField = (name: string) => {
        const startIndex = FIELDS_QUEUE.findIndex((i) => i === name);

        if (startIndex < 0) return;

        for (let i = startIndex + 1; i < FIELDS_QUEUE.length; i++) {
            setValue(`backend.${FIELDS_QUEUE[i]}`, null);
        }
    };

    const getOnChangeSelectFormField = (fieldName: string) => () => {
        clearFieldByQueueFromField(fieldName);
        onChangeFormField();
    };

    const setVPCSubnetFormValue = ({ vpc, subnet }: { vpc: string; subnet: string }) => {
        setValue(`backend.${FIELD_NAMES.VPC}`, vpc);
        setValue(`backend.${FIELD_NAMES.SUBNET}`, subnet);
    };

    const onChangeVPCSubnet = () => {
        const vpcSubnet = getValues(`backend.${FIELD_NAMES.VPC_SUBNET}`);

        if (!vpcSubnet) return;

        const optionItem = subnetOptions.find((i) => i.value === vpcSubnet);

        if (!optionItem) return;

        setVPCSubnetFormValue({
            vpc: optionItem.vpc,
            subnet: optionItem.subnet,
        });
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
                                    setValue(`backend.${FIELD_NAMES.CREDENTIALS}`, text);
                                    setValue(`backend.${FIELD_NAMES.CREDENTIALS_FILENAME}`, file.name);
                                    onChangeFormField();
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
                    name={`backend.${FIELD_NAMES.AREA}`}
                    options={areaOptions}
                    onChange={getOnChangeSelectFormField(FIELD_NAMES.AREA)}
                    disabled={disabledFields || !areaOptions.length}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />

                <FormSelect
                    label={t('projects.edit.gcp.region')}
                    description={t('projects.edit.gcp.region_description')}
                    placeholder={t('projects.edit.gcp.region_placeholder')}
                    control={control}
                    name={`backend.${FIELD_NAMES.REGION}`}
                    options={regionOptions}
                    onChange={getOnChangeSelectFormField(FIELD_NAMES.REGION)}
                    disabled={disabledFields || !regionOptions.length}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />

                <FormSelect
                    label={t('projects.edit.gcp.zone')}
                    description={t('projects.edit.gcp.zone_description')}
                    placeholder={t('projects.edit.gcp.zone_placeholder')}
                    control={control}
                    name={`backend.${FIELD_NAMES.ZONE}`}
                    options={zoneOptions}
                    onChange={getOnChangeSelectFormField(FIELD_NAMES.ZONE)}
                    disabled={disabledFields || !zoneOptions.length}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />

                <FormSelect
                    label={t('projects.edit.gcp.bucket_name')}
                    description={t('projects.edit.gcp.bucket_name_description')}
                    placeholder={t('projects.edit.gcp.bucket_name_placeholder')}
                    control={control}
                    name={`backend.${FIELD_NAMES.BUCKET_NAME}`}
                    options={bucketNameOptions}
                    onChange={getOnChangeSelectFormField(FIELD_NAMES.BUCKET_NAME)}
                    disabled={disabledFields || !bucketNameOptions.length}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />

                <FormSelect
                    label={t('projects.edit.gcp.subnet')}
                    description={t('projects.edit.gcp.subnet_description')}
                    placeholder={t('projects.edit.gcp.subnet_placeholder')}
                    control={control}
                    name={`backend.${FIELD_NAMES.VPC_SUBNET}`}
                    options={subnetOptions}
                    onChange={onChangeVPCSubnet}
                    disabled={disabledFields || !subnetOptions.length}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />
            </SpaceBetween>
        </>
    );
};
