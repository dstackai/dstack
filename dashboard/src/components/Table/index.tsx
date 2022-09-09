import React from 'react';
import { ITableColumn } from './types';
import css from './index.module.css';
import { TABLE_DEFAULT_COLUMN_WIDTH } from 'consts';
import cn from 'classnames';
export { default as Row } from './Row';
export { default as Cell } from './Cell';

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    columns: Array<ITableColumn>;
    children?: React.ReactNode;
    withCheckbox?: boolean;
    withContextMenu?: boolean;
    tableHeadClassName?: string;
}

const Table: React.FC<Props> = ({
    children,
    columns,
    withCheckbox,
    withContextMenu,
    className,
    tableHeadClassName,
    ...props
}) => {
    return (
        <div className={cn(css.table, className, { [css.withCheckbox]: withCheckbox })} {...props}>
            <div className={cn(css.head, tableHeadClassName)}>
                {columns.map((col, index) => {
                    if (col.hidden) return null;

                    return (
                        <div
                            className={cn(css.headCell, { [css.stretch]: col.isStretch })}
                            key={index}
                            style={{ [col.isStretch ? 'minWidth' : 'width']: `${col.width ?? TABLE_DEFAULT_COLUMN_WIDTH}px` }}
                        >
                            {col.title}
                        </div>
                    );
                })}

                {withContextMenu && <div className={cn(css.headCell, css.contextMenuCell)} />}
            </div>
            {children}
        </div>
    );
};

export default Table;
