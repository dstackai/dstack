import React from 'react';
import { useTranslation } from 'react-i18next';

import { Header, Pagination, Table } from 'components';

import { useCollection } from 'hooks';

import { useColumnsDefinitions } from './hooks';

export interface Props {
    projectName: string;
    runName: string;
    jobs: IRun['jobs'];
}

export const JobList: React.FC<Props> = ({ jobs, projectName, runName }) => {
    const { t } = useTranslation();
    const { columns } = useColumnsDefinitions({ projectName, runName });

    const { items, collectionProps, paginationProps } = useCollection(jobs, {
        pagination: { pageSize: 20 },
    });

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            header={<Header>{t('projects.run.jobs')}</Header>}
            pagination={<Pagination {...paginationProps} />}
        />
    );
};
