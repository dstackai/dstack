import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { debounce } from 'lodash';

import { FormInput, FormMultiselect, FormMultiselectOptions, InfoLink, SpaceBetween, Spinner } from 'components';

import { useHelpPanel, useNotifications } from 'hooks';
import useIsMounted from 'hooks/useIsMounted';
import { isRequestFormErrors2, isRequestFormFieldError } from 'libs';
import { useBackendValuesMutation } from 'services/backend';

import { API_KEY_HELP, FIELD_NAMES, REGIONS_HELP } from './constants';

import { IProps } from './types';

import styles from '../AWS/styles.module.scss';

export const LambdaBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const { control, getValues, setValue, setError, clearErrors } = useFormContext();
    const [valuesData, setValuesData] = useState<IAwsBackendValues | undefined>();
    const [regions, setRegions] = useState<FormMultiselectOptions>([]);
    const lastUpdatedField = useRef<string | null>(null);
    const isFirstRender = useRef<boolean>(true);
    const isMounted = useIsMounted();

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();

    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);

    const [openHelpPanel] = useHelpPanel();

    const changeFormHandler = async () => {
        const formValues = getValues();

        if (!formValues.creds.api_key) {
            return;
        }

        clearErrors();

        try {
            const request = getBackendValues(formValues);
            requestRef.current = request;

            const response = await request.unwrap();

            if (!isMounted()) return;

            setValuesData(response);

            lastUpdatedField.current = null;

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

    const getOnChangeSelectField = (fieldName: string) => () => {
        lastUpdatedField.current = fieldName;
        if (requestRef.current) requestRef.current.abort();
        changeFormHandler().catch(console.log);
    };
    const onChangeCredentialField = () => {
        if (requestRef.current) requestRef.current.abort();
        debouncedChangeFormHandler();
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
        let disabledField = loading || !valuesData;

        disabledField = disabledField || (lastUpdatedField.current !== fieldName && isLoadingValues);

        return disabledField;
    };

    return (
        <SpaceBetween size="l">
            <FormInput
                info={<InfoLink onFollow={() => openHelpPanel(API_KEY_HELP)} />}
                label={t('projects.edit.lambda.api_key')}
                description={t('projects.edit.lambda.api_key_description')}
                control={control}
                name={FIELD_NAMES.API_KEY}
                onChange={onChangeCredentialField}
                disabled={loading}
                rules={{ required: t('validation.required') }}
                autoComplete="off"
            />

            <FormMultiselect
                info={<InfoLink onFollow={() => openHelpPanel(REGIONS_HELP)} />}
                label={t('projects.edit.lambda.regions')}
                description={t('projects.edit.lambda.regions_description')}
                placeholder={t('projects.edit.lambda.regions_placeholder')}
                control={control}
                name={FIELD_NAMES.REGIONS}
                onChange={getOnChangeSelectField(FIELD_NAMES.REGIONS)}
                disabled={getDisabledByFieldName(FIELD_NAMES.REGIONS)}
                secondaryControl={renderSpinner()}
                rules={{ required: t('validation.required') }}
                options={regions}
            />
        </SpaceBetween>
    );
};
