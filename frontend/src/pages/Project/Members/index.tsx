import React, { useEffect, useMemo, useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button, FormSelect, Header, Link, ListEmptyMessage, Pagination, SpaceBetween, Table } from 'components';

import { useAppSelector, useCollection, useNotifications } from 'hooks';
import { selectUserData } from 'App/slice';
import { ROUTES } from 'routes';
import { useGetUserListQuery } from 'services/user';
import { useAddProjectMemberMutation, useRemoveProjectMemberMutation } from 'services/project';

import { UserAutosuggest } from './UsersAutosuggest';

import { IProps, TFormValues, TProjectMemberWithIndex } from './types';
//TODO move type to special file
import { TRoleSelectOption } from 'pages/User/Form/types';

import styles from './styles.module.scss';

export const ProjectMembers: React.FC<IProps> = ({ members, loading, onChange, readonly, isAdmin, project }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [selectedItems, setSelectedItems] = useState<TProjectMemberWithIndex[]>([]);
    const { data: usersData } = useGetUserListQuery();
    const userData = useAppSelector(selectUserData);
    const [addMember, { isLoading: isAdding }] = useAddProjectMemberMutation();
    const [removeMember, { isLoading: isRemoving }] = useRemoveProjectMemberMutation();

    const { handleSubmit, control, getValues, setValue } = useForm<TFormValues>({
        defaultValues: { members: members ?? [] },
    });

    const { fields, append, remove } = useFieldArray({
        control,
        name: 'members',
    });

    const currentUserRole = useMemo(() => {
        if (!userData?.username) return null;
        const member = members?.find(m => m.user.username === userData.username);
        return member?.project_role || null;
    }, [members, userData?.username]);

    const isProjectOwner = useMemo(() => {
        return userData?.username === project?.owner.username;
    }, [userData?.username, project?.owner.username]);

    const isMember = currentUserRole !== null;
    const isMemberActionLoading = isAdding || isRemoving;

    const handleJoinProject = async () => {
        if (!userData?.username || !project) return;
        
        try {
            await addMember({
                project_name: project.project_name,
                username: userData.username,
                project_role: 'user',
            }).unwrap();
            
            pushNotification({
                type: 'success',
                content: t('projects.join_success'),
            });
        } catch (error) {
            console.error('Failed to join project:', error);
            pushNotification({
                type: 'error',
                content: t('projects.join_error'),
            });
        }
    };

    const handleLeaveProject = async () => {
        if (!userData?.username || !project) return;
        
        try {
            await removeMember({
                project_name: project.project_name,
                username: userData.username,
            }).unwrap();
            
            pushNotification({
                type: 'success',
                content: t('projects.leave_success'),
            });
            
            // Redirect to project list after successfully leaving
            navigate(ROUTES.PROJECT.LIST);
        } catch (error) {
            console.error('Failed to leave project:', error);
            pushNotification({
                type: 'error',
                content: t('projects.leave_error'),
            });
        }
    };

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
                <Button
                    key="delete"
                    formAction="none"
                    onClick={deleteSelectedMembers}
                    disabled={!selectedItems.length}
                >
                    {t('common.delete')}
                </Button>
            );
        }

        // Add join/leave button if user is authenticated (available even in readonly mode)
        if (userData?.username && project) {
            if (!isMember) {
                actions.unshift(
                    <Button
                        key="join"
                        onClick={handleJoinProject}
                        disabled={isMemberActionLoading}
                        variant="primary"
                    >
                        {isMemberActionLoading ? t('common.loading') : t('projects.join')}
                    </Button>
                );
            } else {
                // Prevent owners and admins from leaving their projects
                const canLeave = !isProjectOwner && currentUserRole !== 'admin';
                
                actions.unshift(
                    <Button
                        key="leave"
                        onClick={handleLeaveProject}
                        disabled={isMemberActionLoading || !canLeave}
                        variant="normal"
                    >
                        {!canLeave 
                            ? t('projects.owner_cannot_leave')
                            : isMemberActionLoading 
                                ? t('common.loading') 
                                : t('projects.leave')
                        }
                    </Button>
                );
            }
        }

        return actions.length > 0 ? <SpaceBetween size="xs" direction="horizontal">{actions}</SpaceBetween> : undefined;
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
        // eslint-disable-next-line @typescript-eslint/no-empty-function
        <form onSubmit={handleSubmit(() => {})}>
            <Table
                selectionType="multi"
                selectedItems={selectedItems}
                onSelectionChange={(event) => setSelectedItems(event.detail.selectedItems)}
                columnDefinitions={COLUMN_DEFINITIONS}
                items={items}
                header={
                    <Header
                        variant="h2"
                        counter={`(${items?.length})`}
                        actions={renderMemberActions()}
                    >
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
