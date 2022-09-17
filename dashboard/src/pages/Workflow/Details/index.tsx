import React, { useMemo, useState } from 'react';
import cn from 'classnames';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import ConfirmStop from 'pages/Runs/components/ConfirmStop';
import Sidebar from 'components/details/DetailsSidebar';
import { isFinishedStatus } from 'libs/status';
import {
    useDeleteMutation,
    useGetWorkflowQuery,
    useRefetchWorkflowMutation,
    useRemoveTagMutation,
    useRestartMutation,
    useStopMutation,
} from 'services/workflows';
import Button from 'components/Button';
import Tag from 'components/Tag';
import Status from 'components/Status';
import Logs from 'features/Logs';
import { selectHasLogs } from 'features/Logs/slice';
import { showAppsModal } from 'features/Run/AppsModal/slice';
import Artifacts from 'features/Artifacts';
import { useAppDispatch, useAppProgress, useAppSelector } from 'hooks';
import { getDateAgoSting, goToUrl, stopPropagation } from 'libs';
import { artifactsToArtifactPaths } from 'libs/artifacts';
import { POLLING_INTERVAL } from 'consts';
import { ReactComponent as RefreshIcon } from 'assets/icons/refresh.svg';
import { ReactComponent as ShapePlusIcon } from 'assets/icons/shape-plus.svg';
import { ReactComponent as DeleteOutlineIcon } from 'assets/icons/delete-outline.svg';
import { ReactComponent as TagMinusIcon } from 'assets/icons/tag-minus.svg';
import { ReactComponent as StopIcon } from 'assets/icons/stop.svg';
import RepoDetailsNavigation from 'pages/Repositories/components/RepoDetailsNavigation';
import ConfirmDeleteRun from 'pages/Runs/components/ConfirmDeleteRun';
import ConfirmRestartRun from 'pages/Runs/components/ConfirmRestartRun';
import EmptyMessage from 'components/EmptyMessage';
import { URL_PARAMS } from 'route/url-params';
import { getRouterModule, RouterModules } from 'route';
import css from './index.module.css';
import { isRunning } from '../../../libs/run';

const WorkflowDetails: React.FC = () => {
    const { t } = useTranslation();
    const dispatch = useAppDispatch();
    const [showConfirmStop, setShowConfirmStop] = useState<boolean>(false);
    const [showConfirmDelete, setShowConfirmDelete] = useState<boolean>(false);
    const [showConfirmRestart, setShowConfirmRestart] = useState<boolean>(false);
    const { userName, repoUserName, repoName, runName, workflowName } = useParams();
    const hasLogs = useAppSelector(selectHasLogs);
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);
    const urlParams = useParams();
    const navigate = useNavigate();

    const {
        data: workflow,
        isLoading: isLoadingWorkflow,
        isFetching: isFetchingWorkflow,
    } = useGetWorkflowQuery({ runName, repoName, repoUserName }, { pollingInterval: POLLING_INTERVAL });

    const hasLogsLocal = useMemo<boolean>(() => {
        if (!workflow) return true;

        return hasLogs[`${workflow.user_name}/${workflow.run_name}`] !== false;
    }, [workflow, hasLogs]);

    const [refetchWorkflow] = useRefetchWorkflowMutation();
    const [restartWorkflow, { isLoading: isRestarting }] = useRestartMutation();
    const [stopWorkflow, { isLoading: isStopping }] = useStopMutation();
    const [removeTag, { isLoading: isRemovingTag }] = useRemoveTagMutation();
    const [deleteWorkflow] = useDeleteMutation();

    useAppProgress(isFetchingWorkflow);

    const finished = useMemo<boolean>(() => !!workflow?.status && isFinishedStatus(workflow?.status), [workflow?.status]);

    const repoLink = useMemo<string>(() => {
        const pathName = ['app', urlParams[URL_PARAMS.REPO_USER_NAME] ? 'user-repouser-repo' : 'user-repo']
            .filter(Boolean)
            .join('.');

        return newRouter.buildUrl(pathName, {
            [URL_PARAMS.USER_NAME]: urlParams[URL_PARAMS.USER_NAME],
            [URL_PARAMS.REPO_USER_NAME]: urlParams[URL_PARAMS.REPO_USER_NAME],
            [URL_PARAMS.REPO_NAME]: urlParams[URL_PARAMS.REPO_NAME],
        });
    }, [urlParams]);

    const userLink = useMemo<string>(() => {
        return newRouter.buildUrl('app.user', {
            [URL_PARAMS.USER_NAME]: urlParams[URL_PARAMS.USER_NAME],
        });
    }, [urlParams]);

    const goToBack = () => navigate(repoLink);
    const refreshHandle = () => refetchWorkflow({ run_name: runName as string, workflow_name: workflowName as string });
    const removeTagHandle = () => removeTag({ run_name: runName as string, workflow_name: workflowName as string });

    const restartHandle = (clear: boolean) => {
        restartWorkflow({
            run_name: runName as IRunWorkflow['run_name'],
            workflow_name: workflowName as IRunWorkflow['workflow_name'],
            clear,
        });

        setShowConfirmRestart(false);
    };

    const confirmStopRun = (abort: boolean) => {
        if (!workflow?.run_name) return;

        stopWorkflow({
            run_name: workflow.run_name,
            workflow_name: workflow.workflow_name,
            abort,
        });

        setShowConfirmStop(false);
    };

    const deleteWorkflowHandle = () => setShowConfirmDelete(true);

    const confirmDeleteWorkflow = () => {
        if (!workflow?.run_name) return;

        setShowConfirmDelete(false);

        deleteWorkflow({
            run_name: workflow.run_name,
            workflow_name: workflow.workflow_name,
        });

        goToBack();
    };

    const showAppsHandle = (event: React.MouseEvent<HTMLButtonElement, MouseEvent>) => {
        stopPropagation(event);
        if (!workflow || !workflow.apps) return;

        if (workflow.apps.length === 1) {
            goToUrl(workflow.apps[0].url, true);
            return;
        }

        dispatch(showAppsModal(workflow.apps));
    };

    if (isLoadingWorkflow) return null;

    return (
        <section className={css.details}>
            <div className={css.topSection}>
                <h2 className={css.repoName}>
                    {userName && (
                        <>
                            <Link to={userLink}>{userName}</Link> /
                        </>
                    )}{' '}
                    <Link to={repoLink}>{repoName}</Link>
                </h2>

                <Button className={css.button} appearance="gray-stroke" icon={<RefreshIcon />} onClick={refreshHandle}>
                    {t('refresh')}
                </Button>
            </div>

            <RepoDetailsNavigation className={css.tabs} />

            {workflow && (
                <div className={css.content}>
                    <div className={css.header}>
                        <Status className={css.status} type={workflow.status} />
                        <h1 className={css.title}>{workflow.workflow_name || t('no_name')}</h1>
                        {workflow.tag_name && <Tag className={css.tag} title={workflow.tag_name} withIcon />}

                        <div className={css.buttons}>
                            {/*{finished && (*/}
                            {/*    <Button*/}
                            {/*        appearance="gray-stroke"*/}
                            {/*        disabled={isRestarting}*/}
                            {/*        displayAsRound*/}
                            {/*        icon={<RefreshIcon />}*/}
                            {/*        onClick={() => setShowConfirmRestart(true)}*/}
                            {/*    />*/}
                            {/*)}*/}

                            {!finished && (
                                <Button
                                    appearance="gray-stroke"
                                    displayAsRound
                                    disabled={isStopping}
                                    icon={<StopIcon />}
                                    onClick={() => setShowConfirmStop(true)}
                                />
                            )}

                            {workflow.tag_name && (
                                <Button
                                    appearance="gray-stroke"
                                    displayAsRound
                                    disabled={isRemovingTag}
                                    onClick={removeTagHandle}
                                    icon={<TagMinusIcon />}
                                />
                            )}

                            {finished && (
                                <Button
                                    appearance="gray-stroke"
                                    displayAsRound
                                    onClick={deleteWorkflowHandle}
                                    icon={<DeleteOutlineIcon />}
                                />
                            )}

                            {isRunning(workflow) && !!workflow.apps?.length && (
                                <Button
                                    className={css.openApp}
                                    appearance="gray-stroke"
                                    icon={<ShapePlusIcon />}
                                    onClick={showAppsHandle}
                                >
                                    {t('open_app', { count: workflow.apps.length })}
                                </Button>
                            )}
                        </div>
                    </div>

                    {!workflow.artifacts?.length && !hasLogsLocal && (
                        <EmptyMessage
                            className={css.emptyMessage}
                            title={t('it_is_pretty_empty')}
                            description={t('you_do_not_have_any_artifacts_and_logs_yet')}
                        />
                    )}

                    {!!workflow.artifacts?.length && (
                        <div className={css.artifactsWrapper}>
                            <div className={css.title}>{t('artifact_other')}</div>

                            <Artifacts
                                workflow_name={workflow.workflow_name}
                                run_name={workflow.run_name}
                                artifacts={artifactsToArtifactPaths(workflow.artifacts)}
                                className={css.artifacts}
                            />
                        </div>
                    )}

                    <div
                        className={cn(css.logsWrapper, { [css['no-artifacts']]: !workflow.artifacts?.length })}
                        style={{ display: hasLogsLocal ? 'flex' : 'none' }}
                    >
                        <div className={css.title}>{t('log_other')}</div>
                        <Logs className={css.logs} run_name={workflow.run_name} user_name={workflow.user_name} />
                    </div>

                    <Sidebar className={css.sidebar}>
                        {workflow && (
                            <>
                                <Sidebar.Property name={t('repository')}>
                                    <Sidebar.RepoAttrs
                                        repoUrl={`https://github.com/${repoUserName}/${repoName}`}
                                        hash={workflow.repo_hash}
                                        branch={workflow.repo_branch}
                                    />

                                    <a
                                        href={`https://github.com/${repoUserName}/${repoName}/commit/${workflow.repo_hash}`}
                                        target="_blank"
                                    >
                                        {t('local_changes')}
                                    </a>

                                    {/*<Link*/}
                                    {/*    to={*/}
                                    {/*        workflow.workflow_name*/}
                                    {/*            ? routes.userRunWorkflowDetailsDiff({*/}
                                    {/*                  userName: workflow.user_name,*/}
                                    {/*                  runName: workflow.run_name,*/}
                                    {/*                  workflowName: workflow.workflow_name,*/}
                                    {/*              })*/}
                                    {/*            : routes.userRunDetailsDiff({*/}
                                    {/*                  userName: workflow.user_name,*/}
                                    {/*                  runName: workflow.run_name,*/}
                                    {/*              })*/}
                                    {/*    }*/}
                                    {/*>*/}
                                    {/*    {t('local_changes')}*/}
                                    {/*</Link>*/}
                                </Sidebar.Property>

                                <Sidebar.Property name={t('workflow')}>
                                    <span className={cn({ [css.gray]: !workflow.workflow_name })}>
                                        {workflow.workflow_name || t('no_name')}
                                    </span>
                                </Sidebar.Property>

                                <Sidebar.Property name={t('submitted')}>
                                    {getDateAgoSting(workflow.submitted_at)}
                                </Sidebar.Property>

                                {/*<Sidebar.Property name={t('updated')}>{getDateAgoSting(workflow.updated_at)}</Sidebar.Property>*/}

                                {/*<Sidebar.Property name={t('variable_other')} align="center">*/}
                                {/*<VariablesCell data={workflow.variables} />*/}
                                {/*</Sidebar.Property>*/}
                            </>
                        )}
                    </Sidebar>
                </div>
            )}

            {showConfirmStop && (
                <ConfirmStop run_name={workflow?.run_name} close={() => setShowConfirmStop(false)} ok={confirmStopRun} />
            )}

            {showConfirmDelete && (
                <ConfirmDeleteRun totalCount={1} close={() => setShowConfirmDelete(false)} ok={confirmDeleteWorkflow} />
            )}

            <ConfirmRestartRun close={() => setShowConfirmRestart(false)} ok={restartHandle} show={showConfirmRestart} />
        </section>
    );
};

export default WorkflowDetails;
