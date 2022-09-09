import React from 'react';
import * as routes from 'routes';
import Header from 'components/details/Header';
import TableContentSkeleton from 'components/TableContentSkeleton';
import Repo from 'components/Repo';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { useGetWorkflowQuery } from 'services/workflows';
import { POLLING_INTERVAL } from 'consts';
import * as Diff2Html from 'diff2html';
import css from './index.module.css';
import cn from 'classnames';

const WorkflowDiff: React.FC = () => {
    const { t } = useTranslation();
    const { runName, workflowName, userName } = useParams();
    const navigate = useNavigate();

    const { data: workflow, isLoading: isLoadingRun } = useGetWorkflowQuery(
        {
            run_name: runName as IRunWorkflow['run_name'],
            workflow_name: workflowName as IRunWorkflow['workflow_name'],
        },
        {
            pollingInterval: POLLING_INTERVAL,
        },
    );

    const back = () => {
        if (!workflow) return;

        if (workflowName) navigate(routes.userRunWorkflowDetails({ userName, runName, workflowName }));
        else navigate(routes.userRunDetails({ userName, runName }));
    };

    const renderDiff = () => {
        return Diff2Html.html(workflow?.repo_diff ?? '', {
            drawFileList: false,
            matching: 'lines',
        });
    };

    if (isLoadingRun)
        return (
            <section className={css.diff}>
                <div>
                    <TableContentSkeleton />
                </div>
            </section>
        );

    return (
        <section className={css.diff}>
            {workflow && (
                <React.Fragment>
                    <Header className={css.header} backClick={back} title={t('local_changes_of', { of: workflow.run_name })} />

                    <Repo className={css.repoAttrs}>
                        <Repo.Url url={workflow.repo_url} />
                        <Repo.Branch branch={workflow.repo_branch} />
                        <Repo.Hash repoUrl={workflow.repo_url} hash={workflow.repo_hash} />
                    </Repo>

                    <div className={css.content} dangerouslySetInnerHTML={{ __html: renderDiff() }} />

                    {workflow.repo_diff ? (
                        <div className={css.content} dangerouslySetInnerHTML={{ __html: renderDiff() }} />
                    ) : (
                        <div className={cn(css.content, css.empty)}>{t('no_local_changes')}</div>
                    )}
                </React.Fragment>
            )}
        </section>
    );
};

export default WorkflowDiff;
