import { Props as StatusProps } from 'components/Status';
import React from 'react';
export type TTableCellDataType = 'text' | 'link' | 'tags' | 'status' | 'artifacts' | 'apps' | 'empty';

export interface ITableColumn {
    name: string;
    title: string;
    width?: number;
    isStretch?: boolean;
    hidden?: boolean;
    type: TTableCellDataType;
}

export abstract interface ITableCell extends Pick<ITableColumn, 'name' | 'width' | 'isStretch' | 'hidden'> {
    dataType: TTableCellDataType;
}

export interface ITableEmptyCell extends ITableCell {
    dataType: 'empty';
}

export interface ITableTextCell extends ITableCell {
    withoutTitle?: boolean;
    dataType: 'text';
    data?: string;
}

export interface ITableLinkCell extends ITableCell {
    dataType: 'link';
    data: {
        title: string;
        to: string;
    };
}

export interface ITableStatusCell extends ITableCell {
    dataType: 'status';
    data: StatusProps;
}

export interface ITableArtifactsCell extends ITableCell {
    dataType: 'artifacts';
    data: IJobArtifactsTableCellData | IWorkflowArtifactsTableCellData;
}

export interface ITableVariablesCell extends ITableCell {
    dataType: 'variables';
    data: TVariables;
}

export interface ITableAppsCell extends ITableCell {
    dataType: 'apps';
    linkProps?: React.HTMLAttributes<HTMLAnchorElement>;
    asLink?: boolean;
    data: TApps;
}

export interface ITag {
    title: string;
    onClick?: () => void;
}

export interface ITableTagsCell extends ITableCell {
    dataType: 'tags';
    data: Array<ITag>;
}

export type TTableCells =
    | ITableEmptyCell
    | ITableTextCell
    | ITableLinkCell
    | ITableTagsCell
    | ITableStatusCell
    | ITableArtifactsCell
    | ITableVariablesCell
    | ITableAppsCell;
