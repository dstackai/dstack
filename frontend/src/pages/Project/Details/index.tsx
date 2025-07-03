import React from 'react';
import { Outlet, useParams } from 'react-router-dom';

import { ContentLayout, DetailsHeader } from 'components';

export const ProjectDetails: React.FC = () => {
    const params = useParams();
    const paramProjectName = params.projectName ?? '';

    return (
        <ContentLayout header={<DetailsHeader title={paramProjectName} />}>
            <Outlet />
        </ContentLayout>
    );
};
