import React, { useEffect, useMemo, useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import {
    Button,
    ButtonWithConfirmation,
    FormInput,
    Header,
    ListEmptyMessage,
    Pagination,
    SpaceBetween,
    Table,
} from 'components';

import { useCollection } from 'hooks';
import { useDeleteSecretsMutation, useGetAllSecretsQuery, useUpdateSecretMutation } from 'services/secrets';

import { IProps, TFormSecretValue, TFormValues, TProjectSecretWithIndex } from './types';

import styles from './styles.module.scss';

export const ProjectSecrets: React.FC<IProps> = ({ project, loading }) => {
    const { t } = useTranslation();
    const [editableRowIndex, setEditableRowIndex] = useState<number | null>(null);
    const projectName = project?.project_name ?? '';

    const { data, isLoading, isFetching } = useGetAllSecretsQuery({ project_name: projectName });
    const [updateSecret, { isLoading: isUpdating }] = useUpdateSecretMutation();
    const [deleteSecret, { isLoading: isDeleting }] = useDeleteSecretsMutation();

    const { handleSubmit, control, getValues, setValue } = useForm<TFormValues>({
        defaultValues: { secrets: [] },
    });

    useEffect(() => {
        if (data) {
            setValue(
                'secrets',
                data.map((s) => ({ ...s, serverId: s.id })),
            );
        }
    }, [data]);

    const { fields, append, remove } = useFieldArray({
        control,
        name: 'secrets',
    });

    const fieldsWithIndex = useMemo(() => {
        return fields.map<TProjectSecretWithIndex>((field, index) => ({ ...field, index }));
    }, [fields]);

    const { items, paginationProps, collectionProps } = useCollection(fieldsWithIndex, {
        filtering: {
            empty: (
                <ListEmptyMessage
                    title={t('projects.edit.secrets.empty_message_title')}
                    message={t('projects.edit.secrets.empty_message_text')}
                />
            ),
        },
        pagination: { pageSize: 10 },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const deleteSelectedSecrets = () => {
        const names = selectedItems?.map((s) => s.name ?? '');

        if (names?.length) {
            deleteSecret({ project_name: projectName, names }).then(() => {
                selectedItems?.forEach((s) => remove(s.index));
            });
        }
    };

    const removeSecretByIndex = (index: number) => {
        const secretData = getValues().secrets?.[index];

        if (!secretData || !secretData.name) {
            return;
        }

        deleteSecret({ project_name: projectName, names: [secretData.name] }).then(() => {
            remove(index);
        });
    };

    const saveSecretByIndex = (index: number) => {
        const secretData = getValues().secrets?.[index];

        if (!secretData || !secretData.name || !secretData.value) {
            return;
        }

        updateSecret({ project_name: projectName, name: secretData.name, value: secretData.value })
            .unwrap()
            .then(() => {
                setEditableRowIndex(null);
            });
    };

    const isDisabledEditableRowActions = loading || isLoading || isFetching || isUpdating;
    const isDisabledNotEditableRowActions = loading || isLoading || isFetching || isDeleting;

    const COLUMN_DEFINITIONS = [
        {
            id: 'name',
            header: t('projects.edit.secrets.name'),
            cell: (field: TFormSecretValue & { index: number }) => {
                const isEditable = editableRowIndex === field.index;

                return (
                    <div className={styles.value}>
                        <div className={styles.valueFieldWrapper}>
                            <FormInput
                                key={field.name}
                                control={control}
                                name={`secrets.${field.index}.name`}
                                disabled={loading || !isEditable || !!field.serverId}
                            />
                        </div>
                    </div>
                );
            },
        },
        {
            id: 'value',
            header: t('projects.edit.secrets.value'),
            cell: (field: TFormSecretValue & { index: number }) => {
                const isEditable = editableRowIndex === field.index;

                return (
                    <div className={styles.value}>
                        <div className={styles.valueFieldWrapper}>
                            <FormInput
                                readOnly={!isEditable}
                                key={field.value}
                                control={control}
                                name={`secrets.${field.index}.value`}
                                disabled={loading || !isEditable}
                            />
                        </div>

                        <div className={styles.buttonsWrapper}>
                            {isEditable && (
                                <Button
                                    disabled={isDisabledEditableRowActions}
                                    formAction="none"
                                    onClick={() => saveSecretByIndex(field.index)}
                                    variant="icon"
                                    iconName="check"
                                />
                            )}

                            {!isEditable && (
                                <Button
                                    disabled={isDisabledNotEditableRowActions}
                                    formAction="none"
                                    onClick={() => setEditableRowIndex(field.index)}
                                    variant="icon"
                                    iconName="edit"
                                />
                            )}

                            {!isEditable && (
                                <ButtonWithConfirmation
                                    disabled={isDisabledNotEditableRowActions}
                                    formAction="none"
                                    onClick={() => removeSecretByIndex(field.index)}
                                    confirmTitle={t('projects.edit.secrets.delete_confirm_title')}
                                    confirmContent={t('projects.edit.secrets.delete_confirm_message')}
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

    const addSecretHandler = () => {
        append({});
        setEditableRowIndex(fields.length);
    };

    const renderActions = () => {
        const actions = [
            <Button key="add" formAction="none" onClick={addSecretHandler}>
                {t('common.add')}
            </Button>,

            <ButtonWithConfirmation
                key="delete"
                disabled={isDisabledNotEditableRowActions || !selectedItems?.length}
                formAction="none"
                onClick={deleteSelectedSecrets}
                confirmTitle={t('projects.edit.secrets.delete_confirm_title')}
                confirmContent={t('projects.edit.secrets.delete_confirm_message')}
            >
                {t('common.delete')}
            </ButtonWithConfirmation>,
        ];

        return actions.length > 0 ? (
            <SpaceBetween size="xs" direction="horizontal">
                {actions}
            </SpaceBetween>
        ) : undefined;
    };

    return (
        <form onSubmit={handleSubmit(() => {})}>
            <Table
                {...collectionProps}
                selectionType="multi"
                columnDefinitions={COLUMN_DEFINITIONS}
                items={items}
                loading={isLoading}
                header={
                    <Header variant="h2" counter={`(${items?.length})`} actions={renderActions()}>
                        {t('projects.edit.secrets.section_title')}
                    </Header>
                }
                pagination={<Pagination {...paginationProps} />}
            />
        </form>
    );
};
