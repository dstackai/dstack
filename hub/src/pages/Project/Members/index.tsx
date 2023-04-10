import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useForm, useFieldArray } from 'react-hook-form';
//TODO move type to special file
import { TRoleSelectOption } from 'pages/User/Form/types';
import { Header, Button, FormSelect, Table, ListEmptyMessage, Link, Pagination } from 'components';
import { ROUTES } from 'routes';
import { useCollection } from 'hooks';
import { IProps, TProjectMemberWithIndex, TFormValues } from './types';
import { UserAutosuggest } from './UsersAutosuggest';
import styles from './styles.module.scss';

export const ProjectMembers: React.FC<IProps> = ({ initialValues, loading, onChange }) => {
    const { t } = useTranslation();
    const [selectedItems, setSelectedItems] = useState<TProjectMemberWithIndex[]>([]);

    const { handleSubmit, control, getValues } = useForm<TFormValues>({
        defaultValues: { members: initialValues ?? [] },
    });

    const { fields, append, remove } = useFieldArray({
        control,
        name: 'members',
    });

    const onChangeHandler = () => onChange(getValues('members'));

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
        { label: t('roles.admin'), value: 'admin' },
        { label: t('roles.run'), value: 'run' },
        { label: t('roles.read'), value: 'read' },
    ];

    const addMember = (user_name: string) => {
        append({
            user_name,
            project_role: 'read',
        });

        onChangeHandler();
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
                <Link target="_blank" href={ROUTES.USER.DETAILS.FORMAT(item.user_name)}>
                    {item.user_name}
                </Link>
            ),
        },
        {
            id: 'global_role',
            header: t('projects.edit.members.role'),
            cell: (field: IProjectMember & { index: number }) => (
                <div className={styles.role}>
                    <div className={styles.roleFieldWrapper}>
                        <FormSelect
                            control={control}
                            name={`members.${field.index}.project_role`}
                            options={roleSelectOptions}
                            disabled={loading}
                            expandToViewport
                            onChange={onChangeHandler}
                        />
                    </div>

                    <div className={styles.deleteMemberButtonWrapper}>
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
                    </div>
                </div>
            ),
        },
    ];

    return (
        // eslint-disable-next-line @typescript-eslint/no-empty-function
        <form onSubmit={handleSubmit(() => {})}>
            <Table
                selectionType="multi"
                trackBy="user_name"
                selectedItems={selectedItems}
                onSelectionChange={(event) => setSelectedItems(event.detail.selectedItems)}
                columnDefinitions={COLUMN_DEFINITIONS}
                items={items}
                header={
                    <Header
                        variant="h2"
                        counter={`(${items?.length})`}
                        actions={
                            <Button formAction="none" onClick={deleteSelectedMembers} disabled={!selectedItems.length}>
                                {t('common.delete')}
                            </Button>
                        }
                    >
                        {t('projects.edit.members.section_title')}
                    </Header>
                }
                filter={
                    <UserAutosuggest
                        disabled={loading}
                        onSelect={({ detail }) => addMember(detail.value)}
                        optionsFilter={(options) => options.filter((o) => !fields.find((f) => f.user_name === o.value))}
                    />
                }
                pagination={<Pagination {...paginationProps} />}
            />
        </form>
    );
};
