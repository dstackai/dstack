import React, { useEffect, useMemo, useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import {
    Button,
    ButtonWithConfirmation,
    FormSelect,
    Header,
    Link,
    ListEmptyMessage,
    Pagination,
    SpaceBetween,
    Table,
} from 'components';

import { useAppSelector, useCollection, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useGetUserListQuery } from 'services/user';

import { selectUserData } from 'App/slice';

import { useProjectMemberActions } from '../hooks/useProjectMemberActions';
import { UserAutosuggest } from './UsersAutosuggest';

import { IProps, TFormValues, TProjectMemberWithIndex } from './types';
//TODO move type to special file
import { TRoleSelectOption } from 'pages/User/Form/types';

import styles from './styles.module.scss';

export const ProjectMembers: React.FC<IProps> = ({ members, loading, onChange, readonly, isAdmin, project }) => {
    const { t } = useTranslation();
    const [selectedItems, setSelectedItems] = useState<TProjectMemberWithIndex[]>([]);
    const { data: usersData } = useGetUserListQuery();
    const userData = useAppSelector(selectUserData);
    const { handleJoinProject, handleLeaveProject, isMemberActionLoading } = useProjectMemberActions();
    const [pushNotification] = useNotifications();

    const { handleSubmit, control, getValues, setValue } = useForm<TFormValues>({
        defaultValues: { members: members ?? [] },
    });

    const { fields, append, remove } = useFieldArray({
        control,
        name: 'members',
    });

    const currentUserRole = useMemo(() => {
        if (!userData?.username) return null;
        const member = members?.find((m) => m.user.username === userData.username);
        return member?.project_role || null;
    }, [members, userData?.username]);

    const isMember = currentUserRole !== null;

    useEffect(() => {
        if (members) {
            setValue('members', members);
        }
    }, [members]);
    const onChangeHandler = () => {
        onChange(getValues('members'));
    };

    const fieldsWithIndex = fields.map<TProjectMemberWithIndex>((field, index) => ({ ...field, index }));

    const { items, paginationProps } = useCollection(fieldsWithIndex, {
        filtering: {
            empty: (
                <ListEmptyMessage
                    title={t('projects.edit.members_empty_message_title')}
                    message={t('projects.edit.members_empty_message_text')}
                />
            ),
        },
        pagination: { pageSize: 10 },
        selection: {},
    });

    const roleSelectOptions: TRoleSelectOption[] = [
        { label: t('roles.admin'), value: 'admin', disabled: !isAdmin },
        { label: t('roles.manager'), value: 'manager' },
        { label: t('roles.user'), value: 'user' },
    ];

    const addMemberHandler = (username: string) => {
        const existingMembers = getValues('members');
        const isDuplicate = existingMembers.some((member) => member.user.username === username);

        if (isDuplicate) {
            pushNotification({
                type: 'error',
                content: `User "${username}" is already a member of this project`,
            });
            return;
        }

        const selectedUser = usersData?.find((u) => u.username === username);

        if (selectedUser) {
            append({
                user: selectedUser,
                project_role: 'user',
            });

            onChangeHandler();
        } else {
            onChange([
                ...getValues('members'),
                {
                    user: {
                        username,
                    },

                    project_role: 'user',
                },
            ]);
        }
    };

    const deleteSelectedMembers = () => {
        remove(selectedItems.map(({ index }) => index));
        setSelectedItems([]);
        onChangeHandler();
    };

    const renderMemberActions = () => {
        const actions = [];

        // Add management actions only if not readonly
        if (!readonly) {
            actions.push(
                <Button key="delete" formAction="none" onClick={deleteSelectedMembers} disabled={!selectedItems.length}>
                    {t('common.delete')}
                </Button>,
            );
        }

        // Add join/leave button if user is authenticated (available even in readonly mode)
        if (userData?.username && project) {
            if (!isMember) {
                actions.unshift(
                    <Button
                        key="join"
                        onClick={() => handleJoinProject(project.project_name, userData.username!)}
                        disabled={isMemberActionLoading}
                        variant="normal"
                    >
                        {isMemberActionLoading ? t('common.loading') : t('projects.join')}
                    </Button>,
                );
            } else {
                // Check if user is the last admin - if so, don't show leave button
                const adminCount = project.members.filter((member) => member.project_role === 'admin').length;
                const isLastAdmin = currentUserRole === 'admin' && adminCount <= 1;

                if (!isLastAdmin) {
                    // Only show leave button if user is not the last admin
                    actions.unshift(
                        <ButtonWithConfirmation
                            key="leave"
                            onClick={() => handleLeaveProject(project.project_name, userData.username!)}
                            disabled={isMemberActionLoading}
                            variant="danger-normal"
                            confirmTitle={t('projects.leave_confirm_title')}
                            confirmContent={t('projects.leave_confirm_message')}
                            confirmButtonLabel={t('projects.leave')}
                        >
                            {isMemberActionLoading ? t('common.loading') : t('projects.leave')}
                        </ButtonWithConfirmation>,
                    );
                }
            }
        }

        return actions.length > 0 ? (
            <SpaceBetween size="xs" direction="horizontal">
                {actions}
            </SpaceBetween>
        ) : undefined;
    };

    const COLUMN_DEFINITIONS = [
        {
            id: 'name',
            header: t('projects.edit.members.name'),
            cell: (item: IProjectMember) => (
                <Link target="_blank" href={ROUTES.USER.DETAILS.FORMAT(item.user.username)}>
                    {item.user.username}
                </Link>
            ),
        },
        {
            id: 'global_role',
            header: t('projects.edit.members.role'),
            cell: (field: IProjectMember & { index: number }) => {
                const isAvailableForAdmin = !readonly && (isAdmin || field.project_role !== 'admin');

                return (
                    <div className={styles.role}>
                        <div className={styles.roleFieldWrapper}>
                            <FormSelect
                                key={field.user.username}
                                control={control}
                                name={`members.${field.index}.project_role`}
                                options={roleSelectOptions}
                                disabled={loading || !isAvailableForAdmin}
                                expandToViewport
                                onChange={onChangeHandler}
                            />
                        </div>

                        <div className={styles.deleteMemberButtonWrapper}>
                            {isAvailableForAdmin && (
                                <Button
                                    disabled={loading}
                                    formAction="none"
                                    onClick={() => {
                                        remove(field.index);
                                        onChangeHandler();
                                    }}
                                    variant="icon"
                                    iconName="remove"
                                />
                            )}
                        </div>
                    </div>
                );
            },
        },
    ];

    return (
        <form onSubmit={handleSubmit(() => {})}>
            <Table
                selectionType="multi"
                selectedItems={selectedItems}
                onSelectionChange={(event) => setSelectedItems(event.detail.selectedItems)}
                columnDefinitions={COLUMN_DEFINITIONS}
                items={items}
                header={
                    <Header variant="h2" counter={`(${items?.length})`} actions={renderMemberActions()}>
                        {t('projects.edit.members.section_title')}
                    </Header>
                }
                filter={
                    readonly ? undefined : (
                        <UserAutosuggest
                            disabled={loading}
                            onSelect={({ detail }) => addMemberHandler(detail.value)}
                            optionsFilter={(options) => options.filter((o) => !fields.find((f) => f.user.username === o.value))}
                        />
                    )
                }
                pagination={<Pagination {...paginationProps} />}
            />
        </form>
    );
};
