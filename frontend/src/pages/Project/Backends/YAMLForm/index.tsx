import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button, FormCodeEditor, FormUI, InfoLink, SpaceBetween } from 'components';

import { useHelpPanel, useNotifications } from 'hooks';
import { isResponseServerError, isResponseServerFormFieldError } from 'libs';

import { CONFIG_YAML_HELP_ENTERPRISE, CONFIG_YAML_HELP_SKY } from './constants';

import { FieldPath } from 'react-hook-form/dist/types/path';

const INFO = process.env.UI_VERSION === 'enterprise' ? CONFIG_YAML_HELP_ENTERPRISE : CONFIG_YAML_HELP_SKY;

export interface IProps {
    initialValues?: IBackendConfigYaml;
    loading?: boolean;
    onCancel: () => void;
    onApply?: (backend: IBackendConfigYaml) => Promise<IBackendConfigYaml | void>;
    onSubmit: (backend: IBackendConfigYaml) => Promise<IBackendConfigYaml | void>;
}

export const YAMLForm: React.FC<IProps> = ({
    initialValues,
    onCancel,
    loading,
    onSubmit: onSubmitProp,
    onApply: onApplyProp,
}) => {
    const { t } = useTranslation();
    const [openHelpPanel] = useHelpPanel();
    const [pushNotification] = useNotifications();
    const [isApplying, setIsApplying] = useState<boolean>(false);

    const { handleSubmit, control, setError, clearErrors } = useForm<IBackendConfigYaml>({
        defaultValues: initialValues,
    });

    const onSubmit = (data: IBackendConfigYaml) => {
        clearErrors();

        const submitCallback = isApplying && onApplyProp ? onApplyProp : onSubmitProp;

        submitCallback(data)
            .finally(() => setIsApplying(false))
            .catch((errorResponse) => {
                const errorRequestData = errorResponse?.data;

                if (isResponseServerError(errorRequestData)) {
                    errorRequestData.detail.forEach((error) => {
                        if (isResponseServerFormFieldError(error)) {
                            setError(error.loc.join('.') as FieldPath<IBackendConfigYaml>, {
                                type: 'custom',
                                message: error.msg,
                            });
                        } else {
                            pushNotification({
                                type: 'error',
                                content: t('common.server_error', { error: error.msg }),
                            });
                        }
                    });
                } else {
                    pushNotification({
                        type: 'error',
                        content: t('common.server_error', { error: errorResponse?.error ?? errorResponse }),
                    });
                }
            });
    };

    return (
        <form onSubmit={handleSubmit(onSubmit)}>
            <FormUI
                actions={
                    <SpaceBetween direction="horizontal" size="xs">
                        <Button formAction="none" disabled={loading} variant="link" onClick={onCancel}>
                            {t('common.cancel')}
                        </Button>

                        {onApplyProp && (
                            <Button loading={loading} disabled={loading} onClick={() => setIsApplying(true)}>
                                {t('common.apply')}
                            </Button>
                        )}

                        <Button loading={loading} disabled={loading} variant="primary">
                            {t('common.save')}
                        </Button>
                    </SpaceBetween>
                }
            >
                <FormCodeEditor
                    info={<InfoLink onFollow={() => openHelpPanel(INFO)} />}
                    control={control}
                    label={t('projects.edit.backend_config')}
                    description={t('projects.edit.backend_config_description')}
                    name="config_yaml"
                    language="yaml"
                    loading={loading}
                    editorContentHeight={600}
                />
            </FormUI>
        </form>
    );
};
