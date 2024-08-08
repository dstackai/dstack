import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { debounce } from 'lodash';

import { FormInput, FormMultiselect, FormMultiselectOptions, FormSelect, InfoLink, SpaceBetween, Spinner } from 'components';

import { useHelpPanel, useNotifications } from 'hooks';
import useIsMounted from 'hooks/useIsMounted';
import { isRequestFormErrors2, isRequestFormFieldError } from 'libs';
import { useBackendValuesMutation } from 'services/backend';
import { AWSCredentialTypeEnum } from 'types';

import { CREDENTIALS_HELP, FIELD_NAMES, REGIONS_HELP, VPC_HELP } from './constants';

import { IProps } from './types';

import styles from './styles.module.scss';

export const AWSBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const { control, getValues, setValue, setError, clearErrors, watch } = useFormContext();
    const [valuesData, setValuesData] = useState<IAwsBackendValues | undefined>();
    const [regions, setRegions] = useState<FormMultiselectOptions>([]);
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
            formValues.creds?.type === AWSCredentialTypeEnum.ACCESS_KEY &&
            (!formValues.creds?.secret_key || !formValues.creds?.access_key)
        ) {
            return;
        }

        if (!formValues.creds?.type) {
            const { creds, ...otherValues } = formValues;

            formValues = otherValues;
        }

        clearErrors();

        try {
            delete formValues.vpc_name;
            const request = getBackendValues(formValues);
            requestRef.current = request;

            const response = await request.unwrap();

            if (!isMounted()) return;

            setValuesData(response);

            lastUpdatedField.current = null;

            setAvailableDefaultCredentials(response.default_creds);

            // select authorization option
            if (!formValues?.creds?.type) {
                setValue(
                    FIELD_NAMES.CREDENTIALS.TYPE,
                    response.default_creds ? AWSCredentialTypeEnum.DEFAULT : AWSCredentialTypeEnum.ACCESS_KEY,
                );

                if (response.default_creds) changeFormHandler().catch(console.log);
            }

            if (response.regions?.values) {
                setRegions(response.regions.values);
            }

            if (response.regions?.selected !== undefined) {
                setValue(FIELD_NAMES.REGIONS, response.regions.selected);
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

            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(VPC_HELP)} />}
                label={t('projects.edit.aws.vpc_name')}
                description={t('projects.edit.aws.vpc_name_description')}
                control={control}
                name={FIELD_NAMES.VPC_NAME}
                disabled={loading}
                autoComplete="off"
            />

            <FormMultiselect
                info={<InfoLink onFollow={() => openHelpPanel(REGIONS_HELP)} />}
                label={t('projects.edit.aws.regions')}
                description={t('projects.edit.aws.regions_description')}
                placeholder={t('projects.edit.aws.regions_placeholder')}
                control={control}
                name={FIELD_NAMES.REGIONS}
                onChange={getOnChangeSelectField(FIELD_NAMES.REGIONS)}
                disabled={getDisabledByFieldName(FIELD_NAMES.REGIONS)}
                secondaryControl={renderSpinner()}
                options={regions}
            />
        </SpaceBetween>
    );
};
