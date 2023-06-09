import React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import {
    Box,
    Button,
    ColumnLayout,
    Container,
    FormField,
    FormInput,
    FormSelect,
    FormUI,
    Header,
    Popover,
    SpaceBetween,
    StatusIndicator,
} from 'components';

import { copyToClipboard } from 'libs';

import { TRoleSelectOption } from './types';

export interface Props {
    initialValues?: IUser;
    loading?: boolean;
    onCancel: () => void;
    onSubmit: (user: IUser) => void;
    onRefreshToken?: () => void;
    disabledRefreshToken?: boolean;
}

export const UserForm: React.FC<Props> = ({
    initialValues,
    onCancel,
    loading,
    onRefreshToken,
    disabledRefreshToken,
    onSubmit: onSubmitProp,
}) => {
    const { t } = useTranslation();
    const isEditing = !!initialValues;

    const { handleSubmit, control } = useForm<IUser>({
        defaultValues: initialValues ?? {
            global_role: 'read',
        },
    });

    const roleSelectOptions: TRoleSelectOption[] = [
        { label: t('roles.admin'), value: 'admin' },
        { label: t('roles.read'), value: 'read' },
    ];

    const onCopyToken = () => {
        copyToClipboard(initialValues?.token ?? '');
    };

    const onSubmit = (data: IUser) => {
        onSubmitProp(data);
    };

    return (
        <form onSubmit={handleSubmit(onSubmit)}>
            <FormUI
                actions={
                    <SpaceBetween direction="horizontal" size="xs">
                        <Button formAction="none" disabled={loading} variant="link" onClick={onCancel}>
                            {t('common.cancel')}
                        </Button>

                        <Button loading={loading} disabled={loading} variant="primary">
                            {t('common.save')}
                        </Button>
                    </SpaceBetween>
                }
            >
                <Container header={<Header variant="h2">{t('users.account_settings')}</Header>}>
                    <SpaceBetween size="l">
                        <ColumnLayout columns={isEditing ? 1 : 2}>
                            {!isEditing && (
                                <FormInput
                                    label={t('users.user_name')}
                                    description={t('users.user_name_description')}
                                    control={control}
                                    name="user_name"
                                    disabled={loading}
                                    rules={{
                                        required: t('validation.required'),

                                        pattern: {
                                            value: /^[a-zA-Z0-9-_]+$/,
                                            message: t('users.edit.validation.user_name_format'),
                                        },
                                    }}
                                />
                            )}

                            <FormSelect
                                label={t('users.global_role')}
                                description={t('users.global_role_description')}
                                control={control}
                                name="global_role"
                                options={roleSelectOptions}
                                disabled={loading}
                            />
                        </ColumnLayout>

                        {initialValues && (
                            <FormField label={t('users.token')} description={t('users.token_description')}>
                                <Box margin={{ right: 'xxs' }} display="inline-block">
                                    <Popover
                                        dismissButton={false}
                                        position="top"
                                        size="small"
                                        triggerType="custom"
                                        content={<StatusIndicator type="success">{t('users.token_copied')}</StatusIndicator>}
                                    >
                                        <Button
                                            disabled={loading}
                                            formAction="none"
                                            iconName="copy"
                                            variant="link"
                                            onClick={onCopyToken}
                                        />
                                    </Popover>
                                </Box>

                                {initialValues.token}

                                <Box margin={{ left: 'l' }} display="inline-block">
                                    <Button
                                        disabled={loading || disabledRefreshToken}
                                        formAction="none"
                                        variant="normal"
                                        onClick={onRefreshToken}
                                    >
                                        {t('users.edit.refresh_token_button_label')}
                                    </Button>
                                </Box>
                            </FormField>
                        )}
                    </SpaceBetween>
                </Container>
            </FormUI>
        </form>
    );
};
