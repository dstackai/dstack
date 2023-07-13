import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { debounce } from 'lodash';

import { FormInput, FormS3BucketSelector, FormSelect, FormSelectOptions, InfoLink, SpaceBetween, Spinner } from 'components';

import { useHelpPanel, useNotifications } from 'hooks';
import { isRequestFormErrors2, isRequestFormFieldError } from 'libs';
import { useBackendValuesMutation } from 'services/project';
import { AWSCredentialTypeEnum } from 'types';

import useIsMounted from '../../../../hooks/useIsMounted';
import { BUCKET_HELP, CREDENTIALS_HELP, FIELD_NAMES, REGION_HELP, SUBNET_HELP } from './constants';

import { IProps } from './types';

import styles from './styles.module.scss';

export const AWSBackend: React.FC<IProps> = ({ loading }) => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const { control, getValues, setValue, setError, clearErrors, watch } = useFormContext();
    const [valuesData, setValuesData] = useState<IProjectAwsBackendValues | undefined>();
    const [regions, setRegions] = useState<FormSelectOptions>([]);
    const [buckets, setBuckets] = useState<TAwsBucket[]>([]);
    const [subnets, setSubnets] = useState<FormSelectOptions>([]);
    const [availableDefaultCredentials, setAvailableDefaultCredentials] = useState<null | boolean>(null);
    const lastUpdatedField = useRef<string | null>(null);
    const isFirstRender = useRef<boolean>(true);
    const isMounted = useIsMounted();

    const [getBackendValues, { isLoading: isLoadingValues }] = useBackendValuesMutation();

    const requestRef = useRef<null | ReturnType<typeof getBackendValues>>(null);

    const [openHelpPanel] = useHelpPanel();

    const backendCredentialTypeValue = watch(`backend.${FIELD_NAMES.CREDENTIALS.TYPE}`);
    const backendAccessKeyValue = watch(`backend.${FIELD_NAMES.CREDENTIALS.ACCESS_KEY}`);
    const backendSecretKeyValue = watch(`backend.${FIELD_NAMES.CREDENTIALS.SECRET_KEY}`);

    const changeFormHandler = async () => {
        let backendFormValues = getValues('backend');

        if (
            backendFormValues.credentials?.type === AWSCredentialTypeEnum.ACCESS_KEY &&
            (!backendFormValues.credentials?.secret_key || !backendFormValues.credentials?.access_key)
        ) {
            return;
        }

        if (!backendFormValues.credentials?.type) {
            const { credentials, ...otherValues } = backendFormValues;

            backendFormValues = otherValues;
        }

        clearErrors('backend');

        try {
            const request = getBackendValues(backendFormValues);
            requestRef.current = request;

            const response = await request.unwrap();

            if (!isMounted()) return;

            setValuesData(response);

            lastUpdatedField.current = null;

            setAvailableDefaultCredentials(response.default_credentials);

            // select authorization option
            if (!backendFormValues?.credentials?.type) {
                setValue(
                    `backend.${FIELD_NAMES.CREDENTIALS.TYPE}`,
                    response.default_credentials ? AWSCredentialTypeEnum.DEFAULT : AWSCredentialTypeEnum.ACCESS_KEY,
                );

                if (response.default_credentials) changeFormHandler().catch(console.log);
            }

            if (response.region_name?.values) {
                setRegions(response.region_name.values);
            }

            if (response.region_name?.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.REGION_NAME}`, response.region_name.selected);
            }

            if (response.s3_bucket_name?.values) {
                setBuckets(response.s3_bucket_name.values);
            }

            if (response.s3_bucket_name?.selected !== undefined) {
                setValue(`backend.${FIELD_NAMES.S3_BUCKET_NAME}`, response.s3_bucket_name.selected);
            }

            if (response.ec2_subnet_id?.values) {
                setSubnets([{ value: '', label: 'No preference' }, ...response.ec2_subnet_id.values]);
            }

            if (response.ec2_subnet_id?.selected !== undefined) {
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
        let disabledField = loading || !backendCredentialTypeValue || !valuesData;

        disabledField =
            disabledField ||
            (backendCredentialTypeValue === AWSCredentialTypeEnum.ACCESS_KEY &&
                (!backendAccessKeyValue || !backendSecretKeyValue));

        disabledField = disabledField || (lastUpdatedField.current !== fieldName && isLoadingValues);

        return disabledField;
    };

    return (
        <SpaceBetween size="l">
            <FormSelect
                label={t('projects.edit.aws.authorization')}
                control={control}
                name={`backend.${FIELD_NAMES.CREDENTIALS.TYPE}`}
                onChange={getOnChangeSelectField(`backend.${FIELD_NAMES.CREDENTIALS.TYPE}`)}
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

            {backendCredentialTypeValue === AWSCredentialTypeEnum.ACCESS_KEY && (
                <>
                    <FormInput
                        info={<InfoLink onFollow={() => openHelpPanel(CREDENTIALS_HELP)} />}
                        label={t('projects.edit.aws.access_key_id')}
                        description={t('projects.edit.aws.access_key_id_description')}
                        control={control}
                        name={`backend.${FIELD_NAMES.CREDENTIALS.ACCESS_KEY}`}
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
                        name={`backend.${FIELD_NAMES.CREDENTIALS.SECRET_KEY}`}
                        onChange={onChangeCredentialField}
                        disabled={loading}
                        rules={{ required: t('validation.required') }}
                        autoComplete="off"
                    />
                </>
            )}

            <FormSelect
                info={<InfoLink onFollow={() => openHelpPanel(REGION_HELP)} />}
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
                info={<InfoLink onFollow={() => openHelpPanel(BUCKET_HELP)} />}
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
                    inContextBrowseButton: 'Choose a bucket',
                    modalBreadcrumbRootItem: 'S3 buckets',
                    modalTitle: 'Choose an S3 bucket',
                }}
            />

            <FormSelect
                info={<InfoLink onFollow={() => openHelpPanel(SUBNET_HELP)} />}
                label={t('projects.edit.aws.ec2_subnet_id')}
                description={t('projects.edit.aws.ec2_subnet_id_description')}
                placeholder={t('projects.edit.aws.ec2_subnet_id_placeholder')}
                control={control}
                name={`backend.${FIELD_NAMES.EC2_SUBNET_ID}`}
                disabled={getDisabledByFieldName(FIELD_NAMES.EC2_SUBNET_ID)}
                onChange={getOnChangeSelectField(FIELD_NAMES.EC2_SUBNET_ID)}
                options={subnets}
                secondaryControl={renderSpinner()}
            />
        </SpaceBetween>
    );
};
