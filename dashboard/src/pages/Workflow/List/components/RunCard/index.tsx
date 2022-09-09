import React, { useState } from 'react';
import cn from 'classnames';
import { useTranslation } from 'react-i18next';
import { Link, LinkProps } from 'react-router-dom';
import Button from 'components/Button';
import { ReactComponent as DotsIcon } from 'assets/icons/dots-vertical.svg';
import { ReactComponent as ClockIcon } from 'assets/icons/clock.svg';
import { ReactComponent as LayersIcon } from 'assets/icons/layers.svg';
import { ReactComponent as ShapePlusIcon } from 'assets/icons/shape-plus.svg';
import { ReactComponent as TagOutlineIcon } from 'assets/icons/tag-outline.svg';
import Dropdown from 'components/Dropdown';
import Status from 'components/Status';
import ProgressBar from 'components/ProgressBar';
import Tooltip from 'components/Tooltip';
import ConfirmStop from 'pages/Runs/components/ConfirmStop';
import ConfirmDeleteRun from 'pages/Runs/components/ConfirmDeleteRun';
import ConfirmRestartRun from 'pages/Runs/components/ConfirmRestartRun';
import AddTag from 'pages/Runs/components/AddTag';
import { showAppsModal } from 'features/Run/AppsModal/slice';
import { showArtifacts } from 'features/ArtifactsModal/slice';
import { useAppDispatch } from 'hooks';
import { getDateAgoSting, goToUrl, stopPropagation } from 'libs';
import { artifactsToArtifactPaths } from 'libs/artifacts';
import { isFailed, isFinished } from 'libs/run';
import { useDeleteMutation, useRestartMutation, useStopMutation } from 'services/workflows';
import css from './index.module.css';

export interface Props extends LinkProps {
    item: IRunWorkflow;
}

const RunCard: React.FC<Props> = ({ className, item, ...props }) => {
    const { t } = useTranslation();
    const finished = isFinished(item);
    const failed = isFailed(item);
    const hasAvailabilityIssues = !!item?.availability_issues?.length;
    const dispatch = useAppDispatch();

    const [showConfirmStop, setShowConfirmStop] = useState<boolean>(false);
    const [showConfirmDelete, setShowConfirmDelete] = useState<boolean>(false);
    const [showConfirmRestart, setShowConfirmRestart] = useState<boolean>(false);
    const [showAddTag, setShowAddTag] = useState<boolean>(false);

    const [restartWorkflow, { isLoading: isRestarting }] = useRestartMutation();
    const [stopWorkflow, { isLoading: isStopping }] = useStopMutation();
    const [deleteWorkflow, { isLoading: isDeleting }] = useDeleteMutation();

    const confirmRestart = (clear: boolean) => {
        restartWorkflow({
            run_name: item.run_name,
            workflow_name: item.workflow_name,
            clear,
        });

        setShowConfirmRestart(false);
    };
    const confirmStopRun = (abort: boolean) => {
        if (!item?.run_name) return;

        stopWorkflow({
            run_name: item.run_name,
            workflow_name: item.workflow_name,
            abort,
        });

        setShowConfirmStop(false);
    };

    const deleteWorkflowHandle = () => setShowConfirmDelete(true);
    const addTagHandle = () => setShowAddTag(true);

    const confirmDeleteWorkflow = () => {
        if (!item?.run_name) return;

        setShowConfirmDelete(false);

        deleteWorkflow({
            run_name: item.run_name,
            workflow_name: item.workflow_name,
        });
    };

    const showAppsHandle = (event: React.MouseEvent<HTMLButtonElement, MouseEvent>) => {
        stopPropagation(event);

        if (!item.apps?.length) return;

        if (item.apps.length === 1) {
            goToUrl(item.apps[0].url, true);
            return;
        }

        dispatch(showAppsModal(item.apps));
    };

    const showArtifactsHandle = (event: React.MouseEvent<HTMLElement, MouseEvent>) => {
        stopPropagation(event);

        dispatch(
            showArtifacts({
                artifacts: artifactsToArtifactPaths(item.artifacts),
                run_name: item.run_name,
                workflow_name: item.workflow_name,
            }),
        );
    };
    return (
        <>
            <Link
                className={cn(css.card, className, { [css.failed]: failed, [css.warning]: hasAvailabilityIssues })}
                {...props}
            >
                <div className={css.topSection}>
                    <Status className={css.icon} type={item.status} availabilityIssues={item.availability_issues} />

                    <div className={cn(css.name, 'mono-font')}>{item.workflow_name || t('no_name')}</div>

                    {item.tag_name && (
                        <Tooltip overlayContent={<div>{item.tag_name}</div>} mouseEnterDelay={1}>
                            <div className={css.tag}>
                                <TagOutlineIcon />
                            </div>
                        </Tooltip>
                    )}

                    <Dropdown
                        items={[
                            {
                                children: t('restart'),
                                onClick: () => setShowConfirmRestart(true),
                                available: false,
                            },
                            {
                                children: t('stop_run'),
                                onClick: () => setShowConfirmStop(true),
                                available: !finished && !isStopping && !isDeleting,
                            },
                            {
                                children: t('delete_run'),
                                onClick: deleteWorkflowHandle,
                                available: finished && !isDeleting,
                            },
                            {
                                children: t('add_tag'),
                                onClick: addTagHandle,
                                available: finished && !isDeleting,
                            },
                        ].filter((i) => i.available)}
                    >
                        <Button
                            className={css.dropdownButton}
                            appearance="gray-transparent"
                            displayAsRound
                            icon={<DotsIcon />}
                            dimension="s"
                        />
                    </Dropdown>
                </div>

                <div className={css.run}>{item.run_name}</div>

                <div className={css.bottomSection}>
                    <ul className={css.points}>
                        <li className={css.point}>
                            <ClockIcon width={12} height={12} />
                            {getDateAgoSting(item.updated_at)}
                        </li>

                        {!!item.artifacts?.length && (
                            <li className={cn(css.point, css.clickable)} onClick={showArtifactsHandle}>
                                <LayersIcon width={11} height={11} />
                                {item.artifacts.length} {t('artifact', { count: item.artifacts.length })}
                            </li>
                        )}
                    </ul>

                    {item.apps?.length ? (
                        <Button
                            className={css.openApp}
                            appearance="gray-stroke"
                            icon={<ShapePlusIcon />}
                            onClick={showAppsHandle}
                        >
                            {t('open_app')}
                        </Button>
                    ) : hasAvailabilityIssues ? (
                        <div className={cn(css.statusText, css.warning)}>{t('avalibility_issues_found')}</div>
                    ) : (
                        <div className={cn(css.statusText, { [css.failed]: failed })}>{t(`statuses.${item.status}`)}</div>
                    )}
                </div>

                {item.status === 'running' && <ProgressBar isActive={true} className={css.progress} />}
            </Link>

            {showConfirmStop && (
                <ConfirmStop run_name={item?.run_name} close={() => setShowConfirmStop(false)} ok={confirmStopRun} />
            )}

            {showConfirmDelete && (
                <ConfirmDeleteRun totalCount={1} close={() => setShowConfirmDelete(false)} ok={confirmDeleteWorkflow} />
            )}

            <ConfirmRestartRun close={() => setShowConfirmRestart(false)} ok={confirmRestart} show={showConfirmRestart} />

            <AddTag
                close={() => setShowAddTag(false)}
                show={showAddTag}
                repo_user_name={item.repo_user_name}
                repo_name={item.repo_name}
                run_name={item.run_name}
            />
        </>
    );
};

export default RunCard;
