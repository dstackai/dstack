import React, { useEffect, useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button, FormSelect, Header, Link, ListEmptyMessage, Pagination, Table } from 'components';

import { useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useGetUserListQuery } from 'services/user';

import { UserAutosuggest } from './UsersAutosuggest';

import { IProps, TFormValues, TProjectMemberWithIndex } from './types';
//TODO move type to special file
import { TRoleSelectOption } from 'pages/User/Form/types';

import styles from './styles.module.scss';

export const ProjectMembers: React.FC<IProps> = ({ members, loading, onChange, readonly, isAdmin }) => {
    const { t } = useTranslation();
    const [selectedItems, setSelectedItems] = useState<TProjectMemberWithIndex[]>([]);
    const { data: usersData } = useGetUserListQuery();

    const { handleSubmit, control, getValues, setValue } = useForm<TFormValues>({
        defaultValues: { members: members ?? [] },
    });

    const { fields, append, remove } = useFieldArray({
        control,
        name: 'members',
    });

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

    const addMember = (username: string) => {
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
                        actions={
                            readonly ? undefined : (
                                <Button formAction="none" onClick={deleteSelectedMembers} disabled={!selectedItems.length}>
                                    {t('common.delete')}
                                </Button>
                            )
                        }
                    >
                        {t('projects.edit.members.section_title')}
                    </Header>
                }
                filter={
                    readonly ? undefined : (
                        <UserAutosuggest
                            disabled={loading}
                            onSelect={({ detail }) => addMember(detail.value)}
                            optionsFilter={(options) => options.filter((o) => !fields.find((f) => f.user.username === o.value))}
                        />
                    )
                }
                pagination={<Pagination {...paginationProps} />}
            />
        </form>
    );
};
