import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';
import { useForm } from 'react-hook-form';
import { ReactComponent as PencilIcon } from 'assets/icons/pencil.svg';
import { ReactComponent as CheckIcon } from 'assets/icons/check.svg';
import { ReactComponent as CloseIcon } from 'assets/icons/close.svg';
import { ReactComponent as AlertCircleOutlineIcon } from 'assets/icons/alert-circle-outline.svg';
import Button from 'components/Button';
import InputField from 'components/form/InputField';
import Field from 'components/form/Field';
import { SHOW_MESSAGE_DURATION } from 'consts';
import { useUpdateAwsConfigMutation } from 'services/user';
import { isErrorWithMessage, wait, compareSimpleObject } from 'libs';
import css from './index.module.css';
import Tooltip from '../../../../components/Tooltip';

type FormValues = Pick<IAWSConfig, 'artifacts_s3_bucket'>;

export interface Props {
    config?: IAWSConfig;
    className?: string;
}

const BucketForm: React.FC<Props> = ({ className, config }) => {
    const { t } = useTranslation();
    const { artifacts_s3_bucket } = config ?? {};
    const [isEditable, setIsEditable] = useState<boolean>(false);
    const [isShowError, setIsShowError] = useState<boolean>(false);
    const [isShowSuccess, setIsShowSuccess] = useState<boolean>(false);

    const [
        updateAWSConfig,
        { isLoading: isUpdating, error: updatingError, isError: isUpdatingError, isSuccess: isUpdatingSuccess },
    ] = useUpdateAwsConfigMutation();

    const { register, setValue, handleSubmit } = useForm<FormValues>();

    const updatingErrorMessage = isErrorWithMessage(updatingError) ? updatingError.data.message : '';

    useEffect(() => {
        if (!isEditable) {
            artifacts_s3_bucket && setValue('artifacts_s3_bucket', artifacts_s3_bucket);
        }
    }, [config]);

    const hideMessages = () => {
        setIsShowError(false);
        setIsShowSuccess(false);
    };

    useEffect(() => {
        if (isUpdating) hideMessages();

        if (isUpdatingSuccess) {
            setIsEditable(false);
            setIsShowSuccess(true);
            wait(SHOW_MESSAGE_DURATION).then(() => hideMessages());
            return;
        }

        if (isUpdatingError) {
            setIsShowError(true);
        }
    }, [isUpdatingSuccess, isUpdatingError, isUpdating]);

    const submit = (values: FormValues) => {
        hideMessages();

        if (!compareSimpleObject(values, { artifacts_s3_bucket })) {
            updateAWSConfig(values);
        } else cancelEditing();
    };

    const editing = () => {
        setIsEditable(true);
        hideMessages();
        setValue('artifacts_s3_bucket', artifacts_s3_bucket ?? '');
    };

    const cancelEditing = () => {
        setIsEditable(false);
        setValue('artifacts_s3_bucket', artifacts_s3_bucket ?? '');
    };

    return (
        <section className={cn(css.section, className)}>
            <h3 className={css.title}>{t('artifact_storage')}</h3>
            <form className={cn(css.form)} onSubmit={handleSubmit(submit)}>
                <InputField
                    {...register('artifacts_s3_bucket')}
                    disabled={!isEditable || isUpdating}
                    label={t('bucket_name')}
                />

                <Field className={css.controlsField} label=" ">
                    <div className={css.buttons}>
                        {!isEditable && (
                            <Button appearance="gray-transparent" displayAsRound icon={<PencilIcon />} onClick={editing} />
                        )}

                        {isEditable && (
                            <React.Fragment>
                                <Button
                                    disabled={isUpdating}
                                    type="submit"
                                    className={css.applyButton}
                                    appearance="gray-transparent"
                                    displayAsRound
                                    icon={<CheckIcon />}
                                />

                                <Button
                                    disabled={isUpdating}
                                    appearance="gray-transparent"
                                    displayAsRound
                                    icon={<CloseIcon />}
                                    onClick={cancelEditing}
                                />
                            </React.Fragment>
                        )}

                        {isUpdating && <div className={cn(css.message)}>{t('verifying')}</div>}

                        {isShowSuccess && (
                            <div className={cn(css.message, 'success')}>
                                {t('verified')} <CheckIcon />
                            </div>
                        )}

                        {isShowError && (
                            <Tooltip
                                {...(updatingErrorMessage === 'non-cancelled requests' ? { visible: false } : {})}
                                overlayContent={t('please_stop_on_demand_runners_before_changing_credentials')}
                                placement="topLeft"
                            >
                                <div className={cn(css.message, 'fail')}>
                                    {t('failed')} <AlertCircleOutlineIcon />
                                </div>
                            </Tooltip>
                        )}
                    </div>
                </Field>
            </form>
        </section>
    );
};

export default BucketForm;
