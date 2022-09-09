import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Modal, { Props as ModalProps } from 'components/Modal';
import Table, { Row, Cell } from 'components/Table';
import { ITableColumn } from 'components/Table/types';
import SearchInput from 'components/SearchInput';
import { arrayToRecordByKeyName } from 'libs';
import { filterVariableByQuery } from 'libs/run';
import { useAppDispatch, useAppSelector } from 'hooks';
import { hideVariablesModal, selectVariables, selectShowModal } from './slice';
import css from './index.module.css';

export type Props = Omit<ModalProps, 'close' | 'show'>;

const columns: ITableColumn[] = [
    {
        name: 'name',
        title: 'Name',
        type: 'text',
        width: 130,
    },
    {
        name: 'value',
        title: 'Value',
        type: 'text',
        isStretch: true,
        width: 150,
    },
];

const mappedColumns: { [key: string]: ITableColumn } = arrayToRecordByKeyName(columns, 'name');

const VariablesModal: React.FC<Props> = ({ ...props }) => {
    const { t } = useTranslation();
    const [searchValue, setSearchValue] = useState<string>('');
    const dispatch = useAppDispatch();
    const variables = useAppSelector(selectVariables);
    const isShow = useAppSelector(selectShowModal);

    const close = () => dispatch(hideVariablesModal());

    const filteredData = useMemo<typeof variables>(() => {
        if (!Array.isArray(variables)) return variables;

        if (!searchValue) return variables;
        return variables.filter((variable) => filterVariableByQuery(variable, searchValue));
    }, [searchValue, variables]);

    return (
        <Modal {...props} show={isShow} close={close}>
            <Modal.Title>{t('variable_other')}</Modal.Title>

            {filteredData && (
                <Modal.Content className={css.content}>
                    <SearchInput
                        placeholder={t('filter_variables')}
                        className={css.search}
                        onChange={(value) => setSearchValue(value)}
                        value={searchValue}
                    />

                    <Table className={css.table} columns={columns}>
                        {filteredData.map((v, index) => (
                            <Row className={css.mainRow} key={index}>
                                <Cell
                                    cell={{
                                        ...mappedColumns['name'],
                                        dataType: 'text',
                                        data: v.key,
                                    }}
                                />
                                <Cell
                                    cell={{
                                        ...mappedColumns['value'],
                                        dataType: 'text',
                                        data: v.value,
                                    }}
                                />
                            </Row>
                        ))}
                    </Table>
                </Modal.Content>
            )}
        </Modal>
    );
};

export default VariablesModal;
