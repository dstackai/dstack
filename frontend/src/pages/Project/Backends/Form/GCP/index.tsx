import React, { useEffect, useRef, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import {
    FileUploader,
    FormMultiselect,
    FormMultiselectOptions,
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
import { GCPCredentialTypeEnum } from 'types';

import { FIELD_NAMES, PROJECT_ID_HELP, REGIONS_HELP, SERVICE_ACCOUNT_HELP } from './constants';

import { IProps } from './types';

import styles from './styles.module.scss';

const FIELDS_QUEUE = [FIELD_NAMES.CREDENTIALS.TYPE, FIELD_NAMES.CREDENTIALS.DATA, FIELD_NAMES.REGIONS];
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
    const [valuesData, setValuesData] = useState<IGCPBackendValues | undefined>();
    const [regionsOptions, setRegionsOptions] = useState<FormMultiselectOptions>([]);
    const [projectIdOptions, setProjectIdOptions] = useState<FormSelectOptions>([]);
    const [availableDefaultCredentials, setAvailableDefaultCredentials] = useState<boolean | null>(null);
    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);
    const [pushNotification] = useNotifications();
    const lastUpdatedField = useRef<string | null>(null);
    const isFirstRender = useRef<boolean>(true);
    const isMounted = useIsMounted();

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();
    const backendCredentialTypeValue = watch(FIELD_NAMES.CREDENTIALS.TYPE);
    const backendCredentials = watch(FIELD_NAMES.CREDENTIALS.DATA);

    const [openHelpPanel] = useHelpPanel();

    const changeFormHandler = async () => {
        const formValues = getValues();

        if (formValues?.creds?.type === GCPCredentialTypeEnum.SERVICE_ACCOUNT && !formValues?.creds?.data) {
            return;
        }

        if (formValues?.creds && !formValues.creds?.type) delete formValues.creds;

        clearErrors();

        try {
            const request = getBackendValues(formValues);
            requestRef.current = request;
            const response = await request.unwrap();

            console.log('response', response);

            if (!isMounted()) return;

            setValuesData(response);

            lastUpdatedField.current = null;

            setAvailableDefaultCredentials(response.default_credentials);
            // If default credentials unavailable, set selected client credential option
            if (!formValues?.creds?.type && !response.default_creds) {
                setValue(FIELD_NAMES.CREDENTIALS.TYPE, GCPCredentialTypeEnum.SERVICE_ACCOUNT);
            }

            // select authorization option
            if (!formValues?.creds?.type) {
                setValue(
                    FIELD_NAMES.CREDENTIALS.TYPE,
                    response.default_credentials ? GCPCredentialTypeEnum.DEFAULT : GCPCredentialTypeEnum.SERVICE_ACCOUNT,
                );

                if (response.default_credentials) changeFormHandler().catch(console.log);
            }

            if (response.regions?.values) {
                setRegionsOptions(response.regions.values);
            }

            if (response.regions?.selected !== undefined) {
                setValue(FIELD_NAMES.REGIONS, response.regions.selected);
            }

            if (response.project_id?.values) {
                setProjectIdOptions(response.project_id.values);
            }

            if (response.project_id?.selected !== undefined) {
                setValue(FIELD_NAMES.PROJECT_ID, response.project_id.selected);
            }
        } catch (errorResponse) {
            console.log('fetch backends values error:', errorResponse);
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-ignore
            const errorRequestData = errorResponse?.data;

            if (isRequestFormErrors2(errorRequestData)) {
                errorRequestData.detail.forEach((error) => {
                    if (isRequestFormFieldError(error)) {
                        if (error.loc.length === 1 && error.loc[0] === 'credentials') {
                            setError(FIELD_NAMES.CREDENTIALS.TYPE, { type: 'custom', message: error.msg });
                        } else {
                            setError(error.loc.join('.'), { type: 'custom', message: error.msg });
                        }
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

        const fileName = getValues(FIELD_NAMES.CREDENTIALS.FILENAME);

        if (fileName) {
            const file = new File([''], fileName, { type: 'text/plain' });
            setFiles([file]);
        }
    }, []);

    const onChangeFormField = () => {
        if (requestRef.current) requestRef.current.abort();
        changeFormHandler().catch(console.log);
    };

    const clearFields = (startIndex: number) => {
        for (let i = startIndex; i < FIELDS_QUEUE.length; i++) {
            setValue(FIELDS_QUEUE[i], null);
        }
    };

    const clearFieldByQueueFromField = (name: string) => {
        const startIndex = FIELDS_QUEUE.findIndex((i) => i === name);
        if (startIndex < 0) return;
        clearFields(startIndex + 1);
    };

    const getOnChangeSelectFormField = (fieldName: string) => () => {
        lastUpdatedField.current = fieldName;
        onChangeFormField();
    };

    const onChangeCredentialsTypeField = () => {
        clearFieldByQueueFromField(FIELD_NAMES.CREDENTIALS.TYPE);
        onChangeFormField();
    };

    const onChangeCredentialField = () => {
        clearFieldByQueueFromField(FIELD_NAMES.CREDENTIALS.DATA);
        onChangeFormField();
    };

    const getDisabledByFieldName = (fieldName: string) => {
        let disabledField = loading || !backendCredentialTypeValue || !valuesData;

        disabledField =
            disabledField || (backendCredentialTypeValue === GCPCredentialTypeEnum.SERVICE_ACCOUNT && !backendCredentials);

        disabledField = disabledField || (lastUpdatedField.current !== fieldName && isLoadingValues);

        switch (fieldName) {
            case FIELD_NAMES.REGIONS:
                disabledField = disabledField || !regionsOptions.length;
                break;
        }

        return disabledField;
    };

    const renderSpinner = (force?: boolean) => {
        if (isLoadingValues || force)
            return (
                <div className={styles.fieldSpinner}>
                    <Spinner />
                </div>
            );
    };

    return (
        <>
            <SpaceBetween size="l">
                <FormSelect
                    label={t('projects.edit.gcp.authorization')}
                    control={control}
                    name={FIELD_NAMES.CREDENTIALS.TYPE}
                    onChange={onChangeCredentialsTypeField}
                    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                    // @ts-ignore
                    errorText={errors?.credentials?.message}
                    disabled={loading || availableDefaultCredentials === null}
                    secondaryControl={availableDefaultCredentials === null && renderSpinner(true)}
                    options={[
                        {
                            label: t('projects.edit.gcp.authorization_default'),
                            value: GCPCredentialTypeEnum.DEFAULT,
                            disabled: !availableDefaultCredentials,
                        },
                        {
                            label: t('projects.edit.gcp.service_account'),
                            value: GCPCredentialTypeEnum.SERVICE_ACCOUNT,
                        },
                    ]}
                />

                {backendCredentialTypeValue === GCPCredentialTypeEnum.SERVICE_ACCOUNT && (
                    <FileUploader
                        info={<InfoLink onFollow={() => openHelpPanel(SERVICE_ACCOUNT_HELP)} />}
                        fileInputId="gcp-credentials"
                        text="Choose a file"
                        description="Upload a service account key JSON file"
                        label={t('projects.edit.gcp.service_account')}
                        accept="application/json"
                        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                        // @ts-ignore
                        errorText={errors?.credentials?.data?.message}
                        files={files}
                        onFilesUploaded={(uploadedFiles) => {
                            if (uploadedFiles.length) {
                                setFiles([...uploadedFiles]);

                                const [file] = uploadedFiles;

                                const reader = new FileReader();
                                reader.onload = function () {
                                    const text = reader.result;
                                    if (text) {
                                        setValue(FIELD_NAMES.CREDENTIALS.DATA, text);
                                        setValue(FIELD_NAMES.CREDENTIALS.FILENAME, file.name);
                                        onChangeCredentialField();
                                    }
                                };

                                reader.readAsText(file);
                            }
                        }}
                    />
                )}

                <FormMultiselect
                    info={<InfoLink onFollow={() => openHelpPanel(REGIONS_HELP)} />}
                    label={t('projects.edit.gcp.regions')}
                    description={t('projects.edit.gcp.regions_description')}
                    placeholder={t('projects.edit.gcp.regions_placeholder')}
                    control={control}
                    name={FIELD_NAMES.REGIONS}
                    options={regionsOptions}
                    onChange={getOnChangeSelectFormField(FIELD_NAMES.REGIONS)}
                    disabled={getDisabledByFieldName(FIELD_NAMES.REGIONS)}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />

                <FormSelect
                    info={<InfoLink onFollow={() => openHelpPanel(PROJECT_ID_HELP)} />}
                    label={t('projects.edit.gcp.project_id')}
                    description={t('projects.edit.gcp.project_id_description')}
                    placeholder={t('projects.edit.gcp.project_id_placeholder')}
                    control={control}
                    name={FIELD_NAMES.PROJECT_ID}
                    options={projectIdOptions}
                    disabled={getDisabledByFieldName(FIELD_NAMES.PROJECT_ID)}
                    rules={{ required: t('validation.required') }}
                    secondaryControl={renderSpinner()}
                />
            </SpaceBetween>
        </>
    );
};
