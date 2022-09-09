import React from 'react';
import { TABLE_DEFAULT_COLUMN_WIDTH } from 'consts';
import { Link } from 'react-router-dom';
import Tag from 'components/Tag';
import Status from 'components/Status';
import { TTableCells, ITableLinkCell, ITableTextCell, ITableTagsCell, ITableStatusCell } from '../types';
import VariablesCell from './VariablesCell';
import ArtifactsCell from './ArtifactsCell';
import AppsCell from './AppsCell';
import css from './index.module.css';
import cn from 'classnames';

const TextCell: React.FC<{ children?: React.ReactNode } & ITableTextCell> = ({ children, data, withoutTitle }) => {
    return (
        <React.Fragment>
            <span title={withoutTitle ? undefined : data}>{data}</span>
            {children}
        </React.Fragment>
    );
};

const LinkCell: React.FC<{ children?: React.ReactNode } & ITableLinkCell> = ({ data }) => {
    return <Link to={data.to}>{data.title}</Link>;
};

const TagsCell: React.FC<{ children?: React.ReactNode } & ITableTagsCell> = ({ children, data }) => {
    return (
        <React.Fragment>
            <div className={css.tags}>
                {data.map((tag, index) => (
                    <Tag className={css.tag} key={index} onClick={tag.onClick} title={tag.title} />
                ))}
            </div>

            {children}
        </React.Fragment>
    );
};

const StatusCell: React.FC<{ children?: React.ReactNode } & ITableStatusCell> = ({ children, data }) => {
    return (
        <React.Fragment>
            <Status {...data} />
            {children}
        </React.Fragment>
    );
};

export interface Props {
    className?: string;
    cell: TTableCells;
    children?: React.ReactNode;
}

const Cell: React.FC<Props> = ({ className, children, cell }) => {
    const renderCellComponent = () => {
        switch (cell.dataType) {
            case 'text':
                return <TextCell {...cell}>{children}</TextCell>;
            case 'link':
                return <LinkCell {...cell}>{children}</LinkCell>;
            case 'tags':
                return <TagsCell {...cell}>{children}</TagsCell>;
            case 'status':
                return <StatusCell {...cell}>{children}</StatusCell>;
            case 'variables':
                return <VariablesCell {...cell}>{children}</VariablesCell>;
            case 'artifacts':
                return <ArtifactsCell {...cell}>{children}</ArtifactsCell>;
            case 'apps':
                return <AppsCell {...cell}>{children}</AppsCell>;
            case 'empty':
                return children;
        }
    };

    if (cell.hidden) return null;

    return (
        <div
            className={cn(css.cell, className, css[cell.dataType], { [css.stretch]: cell.isStretch })}
            style={{ [cell.isStretch ? 'minWidth' : 'width']: `${cell.width ?? TABLE_DEFAULT_COLUMN_WIDTH}px` }}
        >
            {renderCellComponent()}
        </div>
    );
};

export default Cell;
