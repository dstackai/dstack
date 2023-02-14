import React from 'react';
import { useTranslation } from 'react-i18next';
// move type to special file
import { TRoleSelectOption } from 'pages/User/Form/types';
import { Container, Header, FormUI, SpaceBetween, Button, FormInput, FormSelect, Table } from 'components';
import { useForm, useFieldArray } from 'react-hook-form';
import { IProps, TBackendSelectOption } from './types';
import { UserAutosuggest } from './UsersAutosuggest';
import styles from './styles.module.scss';

export const HubForm: React.FC<IProps> = ({ initialValues, onCancel, loading, onSubmit: onSubmitProp }) => {
    const { t } = useTranslation();
    const isEditing = !!initialValues;

    const { handleSubmit, control, watch } = useForm<IHub>({
        defaultValues: initialValues,
    });

    const { fields, append, remove } = useFieldArray({
        control,
        name: 'members',
    });

    const fieldsWithIndex = fields.map((field, index) => ({ ...field, index }));
    const backendType = watch('backend.type');
    const backendSelectOptions: TBackendSelectOption[] = [{ label: t('hubs.backend_type.aws'), value: 'aws' }];

    const roleSelectOptions: TRoleSelectOption[] = [
        { label: t('roles.admin'), value: 'admin' },
        { label: t('roles.run'), value: 'run' },
        { label: t('roles.read'), value: 'read' },
    ];

    const onSubmit = (data: IHub) => {
        onSubmitProp(data);
    };

    const addMember = (user_name: string) => {
        append({
            user_name,
            hub_role: 'read',
        });
    };

    const renderAwsBackendFields = () => {
        return (
            <>
                <FormInput
                    label={t('hubs.edit.aws.access_key')}
                    control={control}
                    name="backend.access_key"
                    disabled={loading}
                />

                <FormInput
                    label={t('hubs.edit.aws.secret_key')}
                    control={control}
                    name="backend.secret_key"
                    disabled={loading}
                />

                <FormInput
                    label={t('hubs.edit.aws.region_name')}
                    control={control}
                    name="backend.region_name"
                    disabled={loading}
                />

                <FormInput
                    label={t('hubs.edit.aws.s3_bucket_name')}
                    control={control}
                    name="backend.s3_bucket_name"
                    disabled={loading}
                />

                <FormInput
                    label={t('hubs.edit.aws.ec2_subnet_id')}
                    control={control}
                    name="backend.ec2_subnet_id"
                    disabled={loading}
                />
            </>
        );
    };

    const renderBackendFields = () => {
        switch (backendType) {
            case 'aws': {
                return renderAwsBackendFields();
            }
            default:
                return null;
        }
    };

    const COLUMN_DEFINITIONS = [
        {
            id: 'name',
            header: t('hubs.edit.members.name'),
            cell: (item: IHubMember) => item.user_name,
        },
        {
            id: 'global_role',
            header: t('hubs.edit.members.role'),
            cell: (field: IHubMember & { index: number }) => (
                <FormSelect
                    control={control}
                    name={`members.${field.index}.hub_role`}
                    options={roleSelectOptions}
                    disabled={loading}
                    expandToViewport
                    secondaryControl={
                        <div className={styles.deleteMemberButtonWrapper}>
                            <Button
                                disabled={loading}
                                formAction="none"
                                onClick={() => remove(field.index)}
                                variant="icon"
                                iconName="remove"
                            />
                        </div>
                    }
                />
            ),
        },
    ];

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
                <SpaceBetween size="l">
                    <Container header={<Header variant="h2">{t('hubs.edit.general_info')}</Header>}>
                        <SpaceBetween size="l">
                            <FormInput
                                label={t('hubs.edit.hub_name')}
                                control={control}
                                name="hub_name"
                                disabled={loading || isEditing}
                            />
                        </SpaceBetween>
                    </Container>

                    <Container header={<Header variant="h2">{t('hubs.edit.cloud_settings')}</Header>}>
                        <SpaceBetween size="l">
                            <FormSelect
                                label={t('users.global_role')}
                                control={control}
                                name="backend.type"
                                options={backendSelectOptions}
                                disabled={loading}
                            />

                            {renderBackendFields()}
                        </SpaceBetween>
                    </Container>

                    <Table
                        columnDefinitions={COLUMN_DEFINITIONS}
                        items={fieldsWithIndex}
                        header={
                            <Header variant="h2" counter={`(${fieldsWithIndex?.length})`}>
                                {t('hubs.edit.members.section_title')}
                            </Header>
                        }
                        filter={
                            <UserAutosuggest
                                disabled={loading}
                                onSelect={({ detail }) => addMember(detail.value)}
                                optionsFilter={(options) => options.filter((o) => !fields.find((f) => f.user_name === o.value))}
                            />
                        }
                    />
                </SpaceBetween>
            </FormUI>
        </form>
    );
};
