import React from 'react';
import { Cell, Row } from 'components/Table';
import { ITableColumn } from 'components/Table/types';
import defaultColumns from './columns';
import css from './index.module.css';
import cn from 'classnames';

export interface Props {
    columns?: Array<ITableColumn>;
    rowsCount?: number;
    rowClassName?: string;
    withRowBorders?: boolean;
}

const TableContentSkeleton: React.FC<Props> = ({
    rowsCount = 7,
    columns = defaultColumns,
    rowClassName,
    withRowBorders = true,
}) => {
    return (
        <React.Fragment>
            {new Array(rowsCount).fill({}).map((r, index) => (
                <Row className={cn(css.row, { [css['with-border']]: withRowBorders }, rowClassName)} key={index}>
                    {columns.map((c, index) => (
                        <Cell
                            key={index}
                            cell={{
                                ...c,
                                dataType: 'empty',
                            }}
                        >
                            <div className={css.animationCell} />
                        </Cell>
                    ))}
                </Row>
            ))}
        </React.Fragment>
    );
};

export default TableContentSkeleton;
