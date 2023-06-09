import React from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate, useParams } from 'react-router-dom';

import { Button, ButtonProps, Container, ContentLayout, DetailsHeader, Loader, SpaceBetween, Tabs } from 'components';

import { useBreadcrumbs } from 'hooks';
import { getRepoDisplayName } from 'libs/repo';
import { ROUTES } from 'routes';
import { useGetProjectRepoQuery } from 'services/project';

import { RepositoryGeneralInfo } from '../components/GeneralInfo';

import { RepoTabTypeEnum } from '../types';

export const RepositoryDetails: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
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

    const goToRepoSettings: ButtonProps['onClick'] = (event) => {
        event.preventDefault();

        navigate(ROUTES.PROJECT.DETAILS.REPOSITORIES.SETTINGS.FORMAT(paramProjectName, paramRepoId));
    };

    const tabs: {
        label: string;
        id: RepoTabTypeEnum;
        href: string;
    }[] = [
        {
            label: t('projects.run.list_page_title'),
            id: RepoTabTypeEnum.RUNS,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.FORMAT(paramProjectName, paramRepoId),
        },

        {
            label: t('projects.tag.list_page_title'),
            id: RepoTabTypeEnum.TAGS,
            href: ROUTES.PROJECT.DETAILS.TAGS.FORMAT(paramProjectName, paramRepoId),
        },
    ];

    return (
        <ContentLayout
            header={
                <DetailsHeader
                    title={displayRepoName}
                    actionButtons={
                        <Button
                            href={ROUTES.PROJECT.DETAILS.REPOSITORIES.SETTINGS.FORMAT(paramProjectName, paramRepoId)}
                            onClick={goToRepoSettings}
                        >
                            {t('common.settings')}
                        </Button>
                    }
                />
            }
        >
            <SpaceBetween size="l">
                {isLoadingRepo && !repoData && (
                    <Container>
                        <Loader />
                    </Container>
                )}

                {repoData && <RepositoryGeneralInfo {...repoData} />}

                <Tabs withNavigation tabs={tabs} />

                <Outlet />
            </SpaceBetween>
        </ContentLayout>
    );
};
