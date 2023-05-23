import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Box, ColumnLayout, Container, ContentLayout, DetailsHeader, Header, Loader } from 'components';

import { useBreadcrumbs } from 'hooks';
import { getRepoDisplayName } from 'libs/repo';
import { ROUTES } from 'routes';
import { useGetProjectRepoQuery } from 'services/project';
import { useGetTagQuery } from 'services/tag';

import { Artifacts } from 'pages/Runs/Details/Artifacts';

import styles from './styles.module.scss';

export const TagDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramRepoId = params.repoId ?? '';
    const paramTagName = params.tagName ?? '';

    const { data: repoData } = useGetProjectRepoQuery({
        name: paramProjectName,
        repo_id: paramRepoId,
    });

    const { data: tagData, isLoading: isLoadingTag } = useGetTagQuery({
        project_name: paramProjectName,
        repo_id: paramRepoId,
        tag_name: paramTagName,
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
        {
            text: t('projects.tags'),
            href: ROUTES.PROJECT.DETAILS.TAGS.FORMAT(paramProjectName, paramRepoId),
        },
        {
            text: paramTagName,
            href: ROUTES.PROJECT.DETAILS.TAGS.DETAILS.FORMAT(paramProjectName, paramRepoId, paramTagName),
        },
    ]);

    return (
        <ContentLayout header={<DetailsHeader title={paramTagName} />}>
            {isLoadingTag && (
                <Container>
                    <Loader />
                </Container>
            )}

            {tagData && (
                <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                    <ColumnLayout columns={4} variant="text-grid">
                        <div>
                            <Box variant="awsui-key-label">{t('projects.tag.run_name')}</Box>
                            <div>{tagData.run_name}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('projects.tag.artifacts')}</Box>
                            <div>{tagData.artifact_heads?.length ?? 0}</div>
                        </div>
                    </ColumnLayout>
                </Container>
            )}

            {tagData && (
                <Artifacts
                    className={styles.artifacts}
                    name={paramProjectName}
                    repo_id={paramRepoId}
                    run_name={tagData.run_name}
                />
            )}
        </ContentLayout>
    );
};
