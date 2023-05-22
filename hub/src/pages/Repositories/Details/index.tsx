import React from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useParams } from 'react-router-dom';
import { format } from 'date-fns';

import { Box, ColumnLayout, Container, ContentLayout, DetailsHeader, Header, Loader, SpaceBetween } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs } from 'hooks';
import { getRepoDisplayName } from 'libs/repo';
import { ROUTES } from 'routes';
import { useGetProjectRepoQuery } from 'services/project';

import { RepoTypeEnum } from '../types';

export const RepositoryDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramRepoId = params.repoId ?? '';

    const { data: repoData, isLoading: isLoadingRepo } = useGetProjectRepoQuery({
        name: paramProjectName,
        repo_id: paramRepoId,
    });

    const displayRepoName = repoData ? getRepoDisplayName(repoData) : 'Loading...';

    useBreadcrumbs([
        {
            text: t('navigation.projects'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            text: t('projects.repositories'),
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            text: displayRepoName,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(paramProjectName, paramRepoId),
        },
    ]);

    return (
        <ContentLayout header={<DetailsHeader title={displayRepoName} />}>
            <SpaceBetween size="l">
                {isLoadingRepo && !repoData && (
                    <Container>
                        <Loader />
                    </Container>
                )}

                {repoData && (
                    <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                        <ColumnLayout columns={4} variant="text-grid">
                            <div>
                                <Box variant="awsui-key-label">{t('projects.repo.card.last_run')}</Box>
                                <div>{format(new Date(repoData.last_run_at), DATE_TIME_FORMAT)}</div>
                            </div>

                            {repoData.repo_info.repo_type === RepoTypeEnum.LOCAL && (
                                <div>
                                    <Box variant="awsui-key-label">{t('projects.repo.card.directory')}</Box>
                                    <div>{repoData.repo_info.repo_dir}</div>
                                </div>
                            )}
                        </ColumnLayout>
                    </Container>
                )}

                <Outlet />
            </SpaceBetween>
        </ContentLayout>
    );
};
