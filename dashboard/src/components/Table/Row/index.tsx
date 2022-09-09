import React, { useMemo } from 'react';
import cn from 'classnames';
import Button, { ButtonProps } from 'components/Button';
import { ReactComponent as PencilIcon } from 'assets/icons/pencil.svg';
import { ReactComponent as DeleteOutlineIcon } from 'assets/icons/delete-outline.svg';
import { ITableColumn } from '../types';
import css from './index.module.css';

export interface Props extends React.HTMLAttributes<HTMLElement> {
    columns?: ITableColumn[];
    tag?: React.ElementType;
    children?: React.ReactNode;
    disabled?: boolean;
}

const TableRow: React.FC<Props> = ({ tag: Tag = 'div', columns, children, className, disabled, ...props }) => {
    const hasStretch = useMemo<boolean>(() => {
        if (!columns) return true;

        return columns.some((c) => c.isStretch);
    }, [columns]);

    return (
        <Tag className={cn(css.row, { [css.stretch]: hasStretch, [css.disabled]: disabled }, className)} {...props}>
            {children}
        </Tag>
    );
};

export interface ContextMenuProps extends React.HTMLAttributes<HTMLDivElement> {
    children?: React.ReactNode;
    autoHidden?: boolean;
}

const RowContextMenu: React.FC<ContextMenuProps> = ({ children, className, autoHidden = true, ...props }) => {
    return (
        <div className={cn(css.contextMenu, className, { [css.autoHidden]: autoHidden })} {...props}>
            {children}
        </div>
    );
};

export interface CheckboxContainerProps extends React.HTMLAttributes<HTMLDivElement> {
    children?: React.ReactNode;
    autoHidden?: boolean;
}

const RowCheckboxContainer: React.FC<CheckboxContainerProps> = ({ children, className, autoHidden = true, ...props }) => {
    return (
        <div className={cn(css.checkboxContainer, className, { [css.autoHidden]: autoHidden })} {...props}>
            {children}
        </div>
    );
};

export type EditButtonProps = ButtonProps;

const RowEditButton: React.FC<EditButtonProps> = ({ className, ...props }) => {
    return (
        <Button
            dimension="xm"
            displayAsRound
            appearance="blue-transparent"
            className={cn(css.rowEditButton, className)}
            icon={<PencilIcon />}
            {...props}
        />
    );
};

export type DeleteButtonProps = ButtonProps;

const RowDeleteButton: React.FC<DeleteButtonProps> = ({ className, ...props }) => {
    return (
        <Button
            dimension="xm"
            displayAsRound
            appearance="red-transparent"
            className={cn(css.rowDeleteButton, className)}
            icon={<DeleteOutlineIcon />}
            {...props}
        />
    );
};

export default Object.assign(TableRow, {
    ContextMenu: RowContextMenu,
    CheckboxContainer: RowCheckboxContainer,
    EditButton: RowEditButton,
    DeleteButton: RowDeleteButton,
});
