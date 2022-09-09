import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';
import { useForm } from 'react-hook-form';
import Modal, { Props as ModalProps } from 'components/Modal';
import Tooltip from 'components/Tooltip';
import Button from 'components/Button';
import InputField from 'components/form/InputField';
import SelectField from 'components/form/SelectField';
import { SHOW_MESSAGE_DURATION } from 'consts';
import { useGetRegionsQuery, useGetSettingsQuery, useUpdateSettingsMutation } from 'services/onDemand';
import { useUpdateAwsConfigMutation, useTestAwsConfigMutation } from 'services/user';
import { regionsToSelectFieldOptions, isErrorWithMessage, wait, compareSimpleObject } from 'libs';
import css from './index.module.css';
import * as yup from 'yup';
import { yupResolver } from '@hookform/resolvers/yup';

const disabledEditRegion = false;

type FormValues = Pick<IAWSConfig, 'aws_access_key_id' | 'aws_secret_access_key' | 'artifacts_s3_bucket' | 'aws_region'>;

const schema = yup
    .object({
        aws_access_key_id: yup.string().required(),
        aws_secret_access_key: yup.string().required(),
        aws_region: yup.string().required(),
    })
    .required();

type MaskedFieldNames = 'aws_access_key_id' | 'aws_secret_access_key';

export interface Props extends ModalProps {
    config?: IAWSConfig;
}

const Form: React.FC<Props> = ({ className, config, ...props }) => {
    const { t } = useTranslation();
    const initialFormValue = config ?? {};
    const [changedFieldNames, setChangedFieldNames] = useState<Set<MaskedFieldNames>>(new Set());
    const [hasSubmitError, setHasSubmitError] = useState<boolean>(false);
    const [testStatus, setTestStatus] = useState<'success' | 'error' | null>(null);

    const isEditing = !!config;

    const [
        updateAWSConfig,
        { isLoading: isUpdating, error: updatingError, isError: isUpdatingError, isSuccess: isUpdatingSuccess },
    ] = useUpdateAwsConfigMutation();

    const { data: regions, isLoading: isLoadingRegions } = useGetRegionsQuery();
    const { data: settings, isLoading: isLoadingSettings } = useGetSettingsQuery();
    const [updateSettings, { isLoading: isUpdatingEnabledAws }] = useUpdateSettingsMutation();

    const [testAws, { isLoading: isTestLoading, error: testingError, isSuccess: isTestingSuccess, isError: isTestingError }] =
        useTestAwsConfigMutation();

    const {
        register,
        setValue,
        handleSubmit,
        getValues,
        reset,
        formState: { errors },
    } = useForm<FormValues>({
        resolver: yupResolver(schema),
        defaultValues: initialFormValue,
    });

    const updatingErrorMessage = isErrorWithMessage(updatingError) ? updatingError.data.message : '';
    const testingErrorMessage = isErrorWithMessage(testingError) ? testingError.data.message : '';

    const hideMessages = () => {
        setHasSubmitError(false);
    };

    useEffect(() => {
        if (!props.show) {
            setChangedFieldNames(new Set());
            wait(300).then(() => resetForm());
        } else resetForm();
    }, [props.show]);

    const resetForm = useCallback(() => {
        if (config) {
            reset(config);
        } else {
            reset({
                aws_access_key_id: '',
                aws_secret_access_key: '',
                artifacts_s3_bucket: '',
                aws_region: '',
            });
        }
    }, [config, reset]);

    useEffect(() => {
        if (isUpdating) hideMessages();

        if (isUpdatingSuccess) {
            props.close();
            wait(SHOW_MESSAGE_DURATION).then(() => hideMessages());
            return;
        }

        if (isUpdatingError) {
            setHasSubmitError(true);
        }
    }, [isUpdatingSuccess, isUpdatingError, isUpdating]);

    useEffect(() => {
        if (isTestingSuccess) {
            setTestStatus('success');
            wait(SHOW_MESSAGE_DURATION).then(() => setTestStatus(null));
            return;
        }

        if (isTestingError) {
            setTestStatus('error');
            wait(SHOW_MESSAGE_DURATION).then(() => setTestStatus(null));
        }
    }, [isTestingSuccess, isTestingError]);

    const onChangeField = (event: React.ChangeEvent<HTMLInputElement>) => {
        const name = event.target.name as MaskedFieldNames;
        setChangedFieldNames((old) => new Set(old).add(name));
    };

    const onBlurField = (event: React.FocusEvent<HTMLInputElement>) => {
        const name = event.target.name as MaskedFieldNames;

        if (!changedFieldNames.has(name) && isEditing) {
            setValue(name, config[name]);
        }
    };

    const onFocusField = (event: React.FocusEvent<HTMLInputElement>) => {
        const name = event.target.name as MaskedFieldNames;
        setValue(name, '');
    };

    const getChangedFields = useCallback(
        (values: FormValues): Partial<IAWSConfig> | null => {
            const { aws_region, artifacts_s3_bucket } = config ?? {};

            const changedRegionOrBucket = !compareSimpleObject(
                {
                    aws_region: values['aws_region'],
                    artifacts_s3_bucket: values['artifacts_s3_bucket'],
                },
                { aws_region, artifacts_s3_bucket },
            );

            if (!(changedRegionOrBucket || changedFieldNames.size)) return null;

            const newValues: Partial<IAWSConfig> = {};

            if (changedRegionOrBucket) {
                newValues['aws_region'] = values['aws_region'];
                newValues['artifacts_s3_bucket'] = values['artifacts_s3_bucket'];
            }

            if (changedFieldNames.size) changedFieldNames.forEach((i) => (newValues[i] = values[i]));

            return newValues;
        },
        [config, changedFieldNames],
    );

    const testHandle = () => {
        setTestStatus(null);
        const currentFormValues = getValues();
        const changedFields = getChangedFields(currentFormValues) ?? {};
        testAws(changedFields);
    };

    const submit = (values: FormValues) => {
        hideMessages();

        const changedFields = getChangedFields(values);
        if (changedFields) updateAWSConfig(changedFields);
        else props.close();
    };

    const toggleEnabledAws = () => {
        if (!settings) return;

        updateSettings({ enabled: !settings.enabled });
    };

    return (
        <Modal className={cn(css.modal, className)} {...props}>
            <form className={css.form} onSubmit={handleSubmit(submit)}>
                <Modal.Title>{t(isEditing ? 'edit_aws_account' : 'new_aws_account')}</Modal.Title>

                <Modal.Content>
                    <InputField
                        className={cn(css.field, { [css.notChanged]: !changedFieldNames.has('aws_access_key_id') })}
                        {...register('aws_access_key_id', {
                            onBlur: onBlurField,
                            onChange: onChangeField,
                        })}
                        onFocus={onFocusField}
                        disabled={isUpdating}
                        label={t('aws_access_key_id')}
                        error={errors.aws_access_key_id}
                    />

                    <InputField
                        className={cn(css.field, { [css.notChanged]: !changedFieldNames.has('aws_secret_access_key') })}
                        {...register('aws_secret_access_key', {
                            onBlur: onBlurField,
                            onChange: onChangeField,
                        })}
                        onFocus={onFocusField}
                        disabled={isUpdating}
                        label={t('aws_secret_access_key')}
                        error={errors.aws_secret_access_key}
                    />

                    <SelectField
                        className={css.field}
                        {...register('aws_region')}
                        disabled={disabledEditRegion || isLoadingRegions || !regions || isUpdating}
                        label={t('region')}
                        placeholder={t('choose_region')}
                        options={regionsToSelectFieldOptions(regions)}
                        error={errors.aws_region}
                    />

                    <InputField
                        className={css.field}
                        {...register('artifacts_s3_bucket')}
                        disabled={isUpdating}
                        label={t('artifacts_s3_bucket')}
                        placeholder={t('optional')}
                        error={errors.artifacts_s3_bucket}
                    />
                </Modal.Content>

                <Modal.Buttons className={css.modalButtons}>
                    <Tooltip
                        placement="right"
                        visible={hasSubmitError}
                        overlayContent={
                            <div>
                                {updatingErrorMessage === 'non-cancelled requests' && (
                                    <div className={cn(css.message, 'fail')}>
                                        {updatingErrorMessage !== 'non-cancelled requests'
                                            ? t('please_stop_on_demand_runners_before_changing_credentials')
                                            : t('failed')}
                                    </div>
                                )}
                                {updatingErrorMessage !== 'non-cancelled requests' && (
                                    <div className={cn(css.message, 'fail')}>
                                        {t('failed')} <div>updatingErrorMessage</div>
                                    </div>
                                )}
                            </div>
                        }
                    >
                        <Button appearance="blue-fill" type="submit" disabled={isUpdating}>
                            {t(isEditing ? 'save' : 'add')}
                        </Button>
                    </Tooltip>

                    <Button appearance="gray-stroke" onClick={props.close} disabled={isUpdating}>
                        {t('cancel')}
                    </Button>

                    <Tooltip
                        placement="right"
                        visible={testStatus !== null}
                        overlayContent={
                            <div>
                                {testStatus === 'success' && <div className={cn(css.message, 'success')}>{t('verified')}</div>}
                                {testStatus === 'error' && (
                                    <div className={cn(css.message, 'fail')}>
                                        {t('failed')}

                                        {testStatus === 'error' && testingErrorMessage && <div>{testingErrorMessage}</div>}
                                    </div>
                                )}
                            </div>
                        }
                    >
                        <div>
                            <Button appearance="gray-stroke" onClick={testHandle} disabled={isTestLoading}>
                                {t('test')}
                            </Button>
                        </div>
                    </Tooltip>

                    {settings && (
                        <Button
                            className={css.toggleButton}
                            appearance="gray-stroke"
                            disabled={isLoadingSettings || isUpdatingEnabledAws}
                            onClick={toggleEnabledAws}
                        >
                            {t(settings.enabled ? 'disable' : 'enable')}
                        </Button>
                    )}
                </Modal.Buttons>
            </form>
        </Modal>
    );
};

export default Form;
