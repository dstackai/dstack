import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { get as _get } from 'lodash';
import { format } from 'date-fns';

import {
    Alert,
    Box,
    Button,
    Code,
    ColumnLayout,
    Container,
    ExpandableSection,
    Header,
    Loader,
    NavigateLink,
    Popover,
    SpaceBetween,
    StatusIndicator,
    Tabs,
    Wizard,
} from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { copyToClipboard } from 'libs';
import { getRunError, getRunPriority, getRunStatusMessage, getStatusIconColor, getStatusIconType } from 'libs/run';
import { ROUTES } from 'routes';
import { useGetRunQuery } from 'services/run';

import { finishedRunStatuses } from 'pages/Runs/constants';
import { runIsStopped } from 'pages/Runs/utils';

import {
    getRunListItemBackend,
    getRunListItemInstanceId,
    getRunListItemPrice,
    getRunListItemRegion,
    getRunListItemResources,
    getRunListItemServiceUrl,
    getRunListItemSpot,
} from '../../List/helpers';
import { JobList } from '../Jobs/List';

import styles from './styles.module.scss';

const UvInstallCommand = 'uv tool install dstack -U';
const PipInstallCommand = 'pip install dstack -U';

export const RunDetails = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunId = params.runId ?? '';

    const { data: runData, isLoading: isLoadingRun } = useGetRunQuery({
        project_name: paramProjectName,
        id: paramRunId,
    });

    const serviceUrl = runData ? getRunListItemServiceUrl(runData) : null;

    const getAttachCommand = (runData: IRun) => {
        const attachCommand = `dstack attach ${runData.run_spec.run_name}`;

        const copyAttachCommand = () => {
            copyToClipboard(attachCommand);
        };

        return [attachCommand, copyAttachCommand] as const;
    };

    const getSSHCommand = (runData: IRun) => {
        const sshCommand = `ssh ${runData.run_spec.run_name}`;

        const copySSHCommand = () => {
            copyToClipboard(sshCommand);
        };

        return [sshCommand, copySSHCommand] as const;
    };

    const [activeStepIndex, setActiveStepIndex] = React.useState(0);

    if (isLoadingRun)
        return (
            <Container>
                <Loader />
            </Container>
        );

    if (!runData) return null;

    const [attachCommand, copyAttachCommand] = getAttachCommand(runData);
    const [sshCommand, copySSHCommand] = getSSHCommand(runData);

    const status = finishedRunStatuses.includes(runData.status)
        ? (runData.latest_job_submission?.status ?? runData.status)
        : runData.status;

    const terminationReason = finishedRunStatuses.includes(runData.status)
        ? runData.latest_job_submission?.termination_reason
        : null;

    const openInIDEUrl = `${runData.run_spec.configuration.ide}://vscode-remote/ssh-remote+${runData.run_spec.run_name}/${runData.run_spec.working_dir || 'workflow'}`;

    return (
        <>
            <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                <ColumnLayout columns={4} variant="text-grid">
                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.project')}</Box>

                        <div>
                            <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(runData.project_name)}>
                                {runData.project_name}
                            </NavigateLink>
                        </div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.repo')}</Box>

                        <div>
                            {_get(runData.run_spec.repo_data, 'repo_name', _get(runData.run_spec.repo_data, 'repo_dir', '-'))}
                        </div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.hub_user_name')}</Box>

                        <div>
                            <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(runData.user)}>{runData.user}</NavigateLink>
                        </div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.configuration')}</Box>
                        <div>{runData.run_spec.configuration_path}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.submitted_at')}</Box>
                        <div>{format(new Date(runData.submitted_at), DATE_TIME_FORMAT)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.finished_at')}</Box>
                        <div>{runData.terminated_at ? format(new Date(runData.terminated_at), DATE_TIME_FORMAT) : '-'}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.status')}</Box>
                        <div>
                            <StatusIndicator
                                type={getStatusIconType(status, terminationReason)}
                                colorOverride={getStatusIconColor(status, terminationReason)}
                            >
                                {getRunStatusMessage(runData)}
                            </StatusIndicator>
                        </div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.error')}</Box>
                        <div>{getRunError(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.priority')}</Box>
                        <div>{getRunPriority(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.cost')}</Box>
                        <div>${runData.cost}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.price')}</Box>
                        <div>{getRunListItemPrice(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.resources')}</Box>
                        <div>{getRunListItemResources(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.region')}</Box>
                        <div>{getRunListItemRegion(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.instance_id')}</Box>
                        <div>{getRunListItemInstanceId(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.spot')}</Box>
                        <div>{getRunListItemSpot(runData)}</div>
                    </div>

                    <div>
                        <Box variant="awsui-key-label">{t('projects.run.backend')}</Box>
                        <div>{getRunListItemBackend(runData)}</div>
                    </div>
                </ColumnLayout>

                {serviceUrl && (
                    <ColumnLayout columns={1} variant="text-grid">
                        <div>
                            <Box variant="awsui-key-label">{t('projects.run.service_url')}</Box>
                            <div>
                                <a href={serviceUrl}>{serviceUrl}</a>
                            </div>
                        </div>
                    </ColumnLayout>
                )}
            </Container>

            {runData.run_spec.configuration.type === 'dev-environment' && !runIsStopped(runData.status) && (
                <Container>
                    <Header variant="h2">Connect</Header>

                    {runData.status === 'running' && (
                        <Wizard
                            i18nStrings={{
                                stepNumberLabel: (stepNumber) => `Step ${stepNumber}`,
                                collapsedStepsLabel: (stepNumber, stepsCount) => `Step ${stepNumber} of ${stepsCount}`,
                                skipToButtonLabel: (step) => `Skip to ${step.title}`,
                                navigationAriaLabel: 'Steps',
                                // cancelButton: "Cancel",
                                previousButton: 'Previous',
                                nextButton: 'Next',
                                optional: 'required',
                            }}
                            onNavigate={({ detail }) => setActiveStepIndex(detail.requestedStepIndex)}
                            activeStepIndex={activeStepIndex}
                            onSubmit={() => window.open(openInIDEUrl, '_blank')}
                            submitButtonText="Open in VS Code"
                            allowSkipTo={true}
                            steps={[
                                {
                                    title: 'Attach',
                                    content: (
                                        <SpaceBetween size="s">
                                            <Box>To access this run, first you need to attach to it.</Box>
                                            <div className={styles.codeWrapper}>
                                                <Code className={styles.code}>{attachCommand}</Code>

                                                <div className={styles.copy}>
                                                    <Popover
                                                        dismissButton={false}
                                                        position="top"
                                                        size="small"
                                                        triggerType="custom"
                                                        content={
                                                            <StatusIndicator type="success">
                                                                {t('common.copied')}
                                                            </StatusIndicator>
                                                        }
                                                    >
                                                        <Button
                                                            formAction="none"
                                                            iconName="copy"
                                                            variant="normal"
                                                            onClick={copyAttachCommand}
                                                        />
                                                    </Popover>
                                                </div>
                                            </div>

                                            <ExpandableSection headerText="No CLI installed?">
                                                <SpaceBetween size="s">
                                                    <Box />
                                                    <Box>To use dstack, install the CLI on your local machine.</Box>

                                                    <Tabs
                                                        variant="container"
                                                        tabs={[
                                                            {
                                                                label: 'uv',
                                                                id: 'uv',
                                                                content: (
                                                                    <>
                                                                        <div className={styles.codeWrapper}>
                                                                            <Code className={styles.code}>
                                                                                {UvInstallCommand}
                                                                            </Code>

                                                                            <div className={styles.copy}>
                                                                                <Popover
                                                                                    dismissButton={false}
                                                                                    position="top"
                                                                                    size="small"
                                                                                    triggerType="custom"
                                                                                    content={
                                                                                        <StatusIndicator type="success">
                                                                                            {t('common.copied')}
                                                                                        </StatusIndicator>
                                                                                    }
                                                                                >
                                                                                    <Button
                                                                                        formAction="none"
                                                                                        iconName="copy"
                                                                                        variant="normal"
                                                                                        onClick={() =>
                                                                                            copyToClipboard(UvInstallCommand)
                                                                                        }
                                                                                    />
                                                                                </Popover>
                                                                            </div>
                                                                        </div>
                                                                    </>
                                                                ),
                                                            },
                                                            {
                                                                label: 'pip',
                                                                id: 'pip',
                                                                content: (
                                                                    <>
                                                                        <div className={styles.codeWrapper}>
                                                                            <Code className={styles.code}>
                                                                                {PipInstallCommand}
                                                                            </Code>

                                                                            <div className={styles.copy}>
                                                                                <Popover
                                                                                    dismissButton={false}
                                                                                    position="top"
                                                                                    size="small"
                                                                                    triggerType="custom"
                                                                                    content={
                                                                                        <StatusIndicator type="success">
                                                                                            {t('common.copied')}
                                                                                        </StatusIndicator>
                                                                                    }
                                                                                >
                                                                                    <Button
                                                                                        formAction="none"
                                                                                        iconName="copy"
                                                                                        variant="normal"
                                                                                        onClick={() =>
                                                                                            copyToClipboard(PipInstallCommand)
                                                                                        }
                                                                                    />
                                                                                </Popover>
                                                                            </div>
                                                                        </div>
                                                                    </>
                                                                ),
                                                            },
                                                        ]}
                                                    />
                                                </SpaceBetween>
                                            </ExpandableSection>
                                        </SpaceBetween>
                                    ),
                                    isOptional: true,
                                },
                                {
                                    title: 'Open',
                                    description: 'After the CLI is attached, you can open the dev environment in VS Code.',
                                    content: (
                                        <SpaceBetween size="s">
                                            <Button
                                                variant="primary"
                                                external={true}
                                                onClick={() => window.open(openInIDEUrl, '_blank')}
                                            >
                                                Open in VS Code
                                            </Button>

                                            <ExpandableSection headerText="Need plain SSH?">
                                                <SpaceBetween size="s">
                                                    <Box />
                                                    <div className={styles.codeWrapper}>
                                                        <Code className={styles.code}>{sshCommand}</Code>

                                                        <div className={styles.copy}>
                                                            <Popover
                                                                dismissButton={false}
                                                                position="top"
                                                                size="small"
                                                                triggerType="custom"
                                                                content={
                                                                    <StatusIndicator type="success">
                                                                        {t('common.copied')}
                                                                    </StatusIndicator>
                                                                }
                                                            >
                                                                <Button
                                                                    formAction="none"
                                                                    iconName="copy"
                                                                    variant="normal"
                                                                    onClick={() => copySSHCommand()}
                                                                />
                                                            </Popover>
                                                        </div>
                                                    </div>
                                                </SpaceBetween>
                                            </ExpandableSection>
                                        </SpaceBetween>
                                    ),
                                    isOptional: true,
                                },
                            ]}
                        />
                    )}

                    {runData.status === 'running' && (
                        <SpaceBetween size="s">
                            <Box />
                            <Alert type="info">Waiting for the run to start.</Alert>
                        </SpaceBetween>
                    )}
                </Container>
            )}

            {runData.jobs.length > 1 && (
                <JobList
                    projectName={paramProjectName}
                    runId={paramRunId}
                    jobs={runData.jobs}
                    runPriority={getRunPriority(runData)}
                />
            )}
        </>
    );
};
