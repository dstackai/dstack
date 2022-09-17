import React, { useMemo } from 'react';
import { Link, Outlet, useParams, Route, Routes, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ReactComponent as GithubIcon } from 'assets/icons/github-circle.svg';
import { ReactComponent as RefreshIcon } from 'assets/icons/refresh.svg';
import { ReactComponent as ChevronDownIcon } from 'assets/icons/chevron-down.svg';
import { ReactComponent as DotsICon } from 'assets/icons/dots-vertical.svg';
import Button from 'components/Button';
import Dropdown from 'components/Dropdown';
import RepoDetailsNavigation from '../components/RepoDetailsNavigation';
import { useRefetchWorkflowsMutation } from 'services/workflows';
import { URL_PARAMS } from 'route/url-params';
import { getRouterModule, RouterModules } from 'route';
import css from './index.module.css';
import { goToUrl } from 'libs';

const RepoDetails: React.FC = () => {
    const { t } = useTranslation();
    const urlParams = useParams();
    const { pathname } = useLocation();
    const { userName, repoUserName, repoName } = urlParams;
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);
    const [refetchWorkflows] = useRefetchWorkflowsMutation();

    const refreshList = () => refetchWorkflows();

    const userLink = useMemo<string>(() => {
        return newRouter.buildUrl('app.user', {
            [URL_PARAMS.USER_NAME]: userName,
        });
    }, [userName]);

    const runsRoute = useMemo<string>(() => {
        const pathName = ['app', urlParams[URL_PARAMS.REPO_USER_NAME] ? 'user-repouser-repo' : 'user-repo', 'repo', 'runs']
            .filter(Boolean)
            .join('.');

        return newRouter.buildUrl(pathName, {
            [URL_PARAMS.USER_NAME]: urlParams[URL_PARAMS.USER_NAME],
            [URL_PARAMS.REPO_USER_NAME]: urlParams[URL_PARAMS.REPO_USER_NAME],
            [URL_PARAMS.REPO_NAME]: urlParams[URL_PARAMS.REPO_NAME],
        });
    }, [urlParams]);

    return (
        <div className={css.details}>
            <div className={css.header}>
                <h1 className={css.title}>
                    {userName && (
                        <>
                            <Link to={userLink}>{userName}</Link> /
                        </>
                    )}{' '}
                    <strong>{repoName}</strong>
                </h1>

                <div className={css.rightSide}>
                    <Button className={css.button} appearance="gray-stroke" icon={<RefreshIcon />} onClick={refreshList}>
                        {t('refresh')}
                    </Button>

                    {pathname === runsRoute && (
                        <Dropdown
                            items={[
                                {
                                    children: t('completed_runs_with_any_status'),
                                    onClick: () => console.log('completed_runs_with_any_status'),
                                },
                                {
                                    children: t('only_failed_runs'),
                                    onClick: () => console.log('only_failed_runs'),
                                },
                                {
                                    children: t('all_runs'),
                                    onClick: () => console.log('all_runs'),
                                },
                            ]}
                        >
                            <Button
                                className={css.button}
                                appearance="gray-stroke"
                                direction="right"
                                icon={<ChevronDownIcon />}
                            >
                                {t('delete_all')}
                            </Button>
                        </Dropdown>
                    )}

                    <Button
                        className={css.button}
                        appearance="gray-stroke"
                        direction="right"
                        onClick={() => goToUrl(`https://github.com/${repoUserName}/${repoName}`, true)}
                        icon={<GithubIcon width={12} height={12} />}
                    >
                        {t('open_in')}
                    </Button>

                    <Dropdown
                        items={[
                            {
                                children: t('delete_repository'),
                                onClick: () => console.log('delete_repository'),
                            },
                        ]}
                    >
                        <Button className={css.button} appearance="gray-stroke" direction="right" icon={<ChevronDownIcon />}>
                            {t('actions')}
                        </Button>
                    </Dropdown>
                </div>
            </div>

            <RepoDetailsNavigation className={css.tabs} />

            <div className={css.content}>
                <Outlet />
            </div>
        </div>
    );
};

export default RepoDetails;
