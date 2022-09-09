import React, { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';
import { ReactComponent as CopyIcon } from 'assets/icons/content-copy.svg';
import Table, { Cell, Row } from 'components/Table';
import Button from 'components/Button';
import { ITableColumn } from 'components/Table/types';
import TableContentSkeleton from 'components/TableContentSkeleton';
import EditModal from './EditModal';
import { useGetSecretsQuery } from 'services/secrets';
import { arrayToRecordByKeyName, copyToClipboard, maskText } from 'libs';
import columns from './columns';
import css from './index.module.css';

export type Props = React.HTMLAttributes<HTMLDivElement>;
const mappedColumns: { [key: string]: ITableColumn } = arrayToRecordByKeyName(columns, 'name');

const Secrets: React.FC<Props> = ({ className, ...props }) => {
    const { t } = useTranslation();
    const [showForm, setShowForm] = useState<boolean>(false);
    const [editableSecret, setEditableSecret] = useState<undefined | ISecret>();

    const { data, isLoading } = useGetSecretsQuery();

    const closeForm = () => {
        setShowForm(false);
        setEditableSecret(undefined);
    };

    const addNew = useCallback(() => setShowForm(true), []);

    const editSecretHandle = useCallback((secret: ISecret) => {
        setEditableSecret(secret);
        setShowForm(true);
    }, []);

    if (isLoading)
        return (
            <div className={cn(css.secrets, className)}>
                <TableContentSkeleton columns={columns} rowsCount={2} />
            </div>
        );

    return (
        <div className={cn(css.secrets, className)} {...props}>
            <Table withContextMenu className={cn(css.table)} columns={columns}>
                {!!data?.length &&
                    data.map((s, index) => (
                        <Row className={css.row} key={index}>
                            <Cell
                                cell={{
                                    ...mappedColumns['secret_name'],
                                    dataType: 'text',
                                    data: s.secret_name,
                                    withoutTitle: true,
                                }}
                            />

                            <Cell
                                cell={{
                                    ...mappedColumns['secret_value'],
                                    dataType: 'text',
                                    data: maskText(s.secret_value.slice(0, 18)),
                                    withoutTitle: true,
                                }}
                            >
                                <Button
                                    className={css.copy}
                                    appearance="gray-transparent"
                                    icon={<CopyIcon />}
                                    onClick={() => copyToClipboard(s.secret_value)}
                                />
                            </Cell>

                            <Row.ContextMenu autoHidden={data.length > 1}>
                                <Row.EditButton onClick={() => editSecretHandle(s)} />
                            </Row.ContextMenu>
                        </Row>
                    ))}
            </Table>

            <Button className={css.addButton} appearance={'blue-fill'} onClick={addNew}>
                {t('add_secret')}
            </Button>

            {showForm && <EditModal close={closeForm} secret={editableSecret} />}
        </div>
    );
};

export default Secrets;
