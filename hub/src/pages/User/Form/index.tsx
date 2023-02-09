import React from 'react';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { Container, Header, FormUI, SpaceBetween, Button, FormInput, FormSelect, Popover, StatusIndicator } from 'components';
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
        defaultValues: initialValues,
    });

    const roleSelectOptions: TRoleSelectOption[] = [
        { label: t('roles.admin'), value: 'admin' },
        { label: t('roles.run'), value: 'run' },
        { label: t('roles.read'), value: 'read' },
    ];

    const onCopyToken = async () => {
        try {
            await navigator.clipboard.writeText(initialValues?.token ?? '');
        } catch (err) {
            console.error('Failed to copy: ', err);
        }
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
                <Container header={<Header variant="h2">{t('users.general_info')}</Header>}>
                    <SpaceBetween size="l">
                        <FormInput
                            label={t('users.user_name')}
                            control={control}
                            name="user_name"
                            disabled={loading || isEditing}
                        />

                        <FormSelect
                            label={t('users.global_role')}
                            control={control}
                            name="global_role"
                            options={roleSelectOptions}
                            disabled={loading}
                        />

                        {initialValues && (
                            <FormInput
                                label={t('users.token')}
                                control={control}
                                name="token"
                                disabled
                                secondaryControl={
                                    <SpaceBetween size="xs" direction="horizontal">
                                        <Popover
                                            dismissButton={false}
                                            position="top"
                                            size="small"
                                            triggerType="custom"
                                            content={
                                                <StatusIndicator type="success">{t('users.token_copied')}</StatusIndicator>
                                            }
                                        >
                                            <Button
                                                disabled={loading}
                                                formAction="none"
                                                iconName="copy"
                                                variant="normal"
                                                onClick={onCopyToken}
                                            />
                                        </Popover>

                                        {onRefreshToken && (
                                            <Button
                                                disabled={loading || disabledRefreshToken}
                                                formAction="none"
                                                iconName="refresh"
                                                variant="normal"
                                                onClick={onRefreshToken}
                                            />
                                        )}
                                    </SpaceBetween>
                                }
                            />
                        )}
                    </SpaceBetween>
                </Container>
            </FormUI>
        </form>
    );
};
