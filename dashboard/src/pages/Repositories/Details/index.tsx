import React, { useMemo, useState } from 'react';
import { Outlet, useParams, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ReactComponent as GithubIcon } from 'assets/icons/github-circle.svg';
import { ReactComponent as RefreshIcon } from 'assets/icons/refresh.svg';
import { ReactComponent as ChevronDownIcon } from 'assets/icons/chevron-down.svg';
import ConfirmModal from 'components/ConfirmModal';
import Button from 'components/Button';
import Dropdown from 'components/Dropdown';
import BreadCrumbs from 'components/BreadCrumbs';
import RepoDetailsNavigation from '../components/RepoDetailsNavigation';
import { useDeleteMutation, useRefetchWorkflowsMutation } from 'services/workflows';
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

    const [showConfirmDeleteAll, setShowConfirmDeleteAll] = useState<boolean>(false);
    const [showConfirmDeleteAllFailed, setShowConfirmDeleteAllFailed] = useState<boolean>(false);

    const refreshList = () => refetchWorkflows();
    const [deleteWorkflow, { isLoading: isDeleting }] = useDeleteMutation();

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

    const confirmDeleteAllRuns = () => {
        if (!repoUserName || !repoName) return;

        deleteWorkflow({
            repo_user_name: repoUserName,
            repo_name: repoName,
            all_run: true,
        });
    };

    const confirmDeleteAllFailedRuns = () => {
        if (!repoUserName || !repoName) return;

        deleteWorkflow({
            repo_user_name: repoUserName,
            repo_name: repoName,
            failed_runs: true,
        });
    };

    return (
        <div className={css.details}>
            <div className={css.header}>
                <div className={css.title}>
                    <BreadCrumbs>
                        <BreadCrumbs.Item to={newRouter.buildUrl('app')}>{t('repository_other')}</BreadCrumbs.Item>
                        <BreadCrumbs.Item>{`${repoUserName}/${repoName}`}</BreadCrumbs.Item>
                    </BreadCrumbs>
                </div>

                <div className={css.rightSide}>
                    <Button className={css.button} appearance="gray-stroke" icon={<RefreshIcon />} onClick={refreshList}>
                        {t('refresh')}
                    </Button>

                    {pathname === runsRoute && (
                        <Dropdown
                            items={[
                                {
                                    children: t('delete_all_runs'),
                                    onClick: () => setShowConfirmDeleteAll(true),
                                },
                                {
                                    children: t('delete_failed_runs'),
                                    onClick: () => setShowConfirmDeleteAllFailed(true),
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

            <ConfirmModal
                title={t('delete_all_runs')}
                confirmButtonProps={{ children: t('delete_all') }}
                ok={confirmDeleteAllRuns}
                show={showConfirmDeleteAll}
                close={() => setShowConfirmDeleteAll(false)}
            >
                {t('confirm_messages.delete_all_runs')}
            </ConfirmModal>

            <ConfirmModal
                title={t('delete_failed_runs')}
                confirmButtonProps={{ children: t('delete') }}
                ok={confirmDeleteAllFailedRuns}
                show={showConfirmDeleteAllFailed}
                close={() => setShowConfirmDeleteAllFailed(false)}
            >
                {t('confirm_messages.delete_failed_runs')}
            </ConfirmModal>
        </div>
    );
};

export default RepoDetails;
