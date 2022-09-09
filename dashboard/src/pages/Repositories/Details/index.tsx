import React, { useMemo } from 'react';
import { Link, Outlet, useParams } from 'react-router-dom';
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

const RepoDetails: React.FC = () => {
    const { t } = useTranslation();
    const { userName, repoName } = useParams();
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);
    const [refetchWorkflows] = useRefetchWorkflowsMutation();
    const refreshList = () => refetchWorkflows();

    const userLink = useMemo<string>(() => {
        return newRouter.buildUrl('app.user', {
            [URL_PARAMS.USER_NAME]: userName,
        });
    }, [userName]);

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
                            onClick={() => console.log('clear')}
                        >
                            {t('clear')}
                        </Button>
                    </Dropdown>

                    <Button
                        className={css.button}
                        appearance="gray-stroke"
                        direction="right"
                        onClick={() => console.log('open_in')}
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
                        <Button appearance="gray-transparent" displayAsRound icon={<DotsICon />} />
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
