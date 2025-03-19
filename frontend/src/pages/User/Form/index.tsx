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

import { TActiveSelectOption, TRoleSelectOption } from './types';

export interface Props {
    initialValues?: IUserWithCreds;
    loading?: boolean;
    onCancel: () => void;
    onSubmit: (user: IUser) => void;
    onRefreshToken?: () => void;
    disabledEmailEndRoleFields?: boolean;
    disabledRefreshToken?: boolean;
}

export const UserForm: React.FC<Props> = ({
    initialValues,
    onCancel,
    loading,
    onRefreshToken,
    disabledEmailEndRoleFields,
    disabledRefreshToken,
    onSubmit: onSubmitProp,
}) => {
    const { t } = useTranslation();
    const isEditing = !!initialValues;

    const { handleSubmit, control } = useForm<IUser>({
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        defaultValues: initialValues
            ? { ...initialValues, active: initialValues.active ? 'active' : 'inactive' }
            : {
                  global_role: 'user',
                  active: 'active',
              },
    });

    const roleSelectOptions: TRoleSelectOption[] = [
        { label: t('roles.admin'), value: 'admin' },
        { label: t('roles.user'), value: 'user' },
    ];

    const activeSelectOptions: TActiveSelectOption[] = [
        { label: t('users.activated'), value: 'active' },
        { label: t('users.deactivated'), value: 'inactive' },
    ];

    const onCopyToken = () => {
        copyToClipboard(initialValues?.creds.token ?? '');
    };

    const onSubmit = (data: IUser) => {
        onSubmitProp({
            ...data,
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-ignore
            active: data.active === 'active',
        });
    };

    const isDisabledEmailAndRoleField = () => {
        return loading || disabledEmailEndRoleFields;
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
                                    name="username"
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

                            <FormInput
                                label={t('users.email')}
                                description={t('users.email_description')}
                                control={control}
                                name="email"
                                disabled={isDisabledEmailAndRoleField()}
                                rules={{
                                    pattern: {
                                        value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
                                        message: t('users.edit.validation.email_format'),
                                    },
                                }}
                            />

                            <FormSelect
                                label={t('users.global_role')}
                                description={t('users.global_role_description')}
                                control={control}
                                name="global_role"
                                options={roleSelectOptions}
                                disabled={isDisabledEmailAndRoleField()}
                            />

                            <FormSelect
                                label={t('users.active')}
                                description={t('users.active_description')}
                                control={control}
                                name="active"
                                options={activeSelectOptions}
                                disabled={isDisabledEmailAndRoleField()}
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

                                {initialValues.creds.token}

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
