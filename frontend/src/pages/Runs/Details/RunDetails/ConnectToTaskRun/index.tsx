import React, { FC } from 'react';
import { useTranslation } from 'react-i18next';

import {
    Alert,
    Box,
    Button,
    ButtonDropdown,
    Code,
    Container,
    ExpandableSection,
    Header,
    Popover,
    SpaceBetween,
    StatusIndicator,
    Tabs,
    Wizard,
} from 'components';

import { copyToClipboard } from 'libs';

import { useConfigProjectCliCommand } from 'pages/Project/hooks/useConfigProjectCliComand';

import styles from '../ConnectToRunWithDevEnvConfiguration/styles.module.scss';

const UvInstallCommand = 'uv tool install dstack -U';
const PipInstallCommand = 'pip install dstack -U';

const getPort = (spec: IAppSpec): number => spec.map_to_port ?? spec.port;

export const ConnectToTaskRun: FC<{ run: IRun }> = ({ run }) => {
    const { t } = useTranslation();

    const attachCommand = `dstack attach ${run.run_spec.run_name} --logs`;
    const appSpecs = run.jobs[0]?.job_spec?.app_specs ?? [];

    const [activeStepIndex, setActiveStepIndex] = React.useState(0);
    const [selectedPort, setSelectedPort] = React.useState(() => getPort(appSpecs[0]));
    const [configCliCommand, copyCliCommand] = useConfigProjectCliCommand({ projectName: run.project_name });

    const openPort = (port: number) => window.open(`http://127.0.0.1:${port}`, '_blank');

    return (
        <Container>
            <Header variant="h2">Connect</Header>

            {run.status === 'running' && (
                <Wizard
                    i18nStrings={{
                        stepNumberLabel: (stepNumber) => `Step ${stepNumber}`,
                        collapsedStepsLabel: (stepNumber, stepsCount) => `Step ${stepNumber} of ${stepsCount}`,
                        skipToButtonLabel: (step) => `Skip to ${step.title}`,
                        navigationAriaLabel: 'Steps',
                        previousButton: 'Previous',
                        nextButton: 'Next',
                        optional: 'required',
                    }}
                    onNavigate={({ detail }) => setActiveStepIndex(detail.requestedStepIndex)}
                    activeStepIndex={activeStepIndex}
                    onSubmit={() => openPort(selectedPort)}
                    submitButtonText={appSpecs.length === 1 ? 'Open port' : `Open port ${selectedPort}`}
                    allowSkipTo
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
                                                content={<StatusIndicator type="success">{t('common.copied')}</StatusIndicator>}
                                            >
                                                <Button
                                                    formAction="none"
                                                    iconName="copy"
                                                    variant="normal"
                                                    onClick={() => copyToClipboard(attachCommand)}
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
                                                                    <Code className={styles.code}>{UvInstallCommand}</Code>

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
                                                                    <Code className={styles.code}>{PipInstallCommand}</Code>

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

                                            <Box>And then configure the project.</Box>

                                            <div className={styles.codeWrapper}>
                                                <Code className={styles.code}>{configCliCommand}</Code>

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
                                                            onClick={copyCliCommand}
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
                        {
                            title: 'Open',
                            description: 'After the CLI is attached, you can open the forwarded ports.',
                            content: (
                                <SpaceBetween size="s">
                                    {appSpecs.length === 1 ? (
                                        <Button
                                            variant="primary"
                                            external={true}
                                            onClick={() => openPort(getPort(appSpecs[0]))}
                                        >
                                            Open port
                                        </Button>
                                    ) : (
                                        <ButtonDropdown
                                            variant="primary"
                                            mainAction={{
                                                text: `Open port ${selectedPort}`,
                                                external: true,
                                                onClick: () => openPort(selectedPort),
                                            }}
                                            items={appSpecs.map((spec) => {
                                                const port = getPort(spec);

                                                return {
                                                    id: String(port),
                                                    text: `Port ${port}`,
                                                    external: true,
                                                };
                                            })}
                                            onItemClick={({ detail }) => {
                                                const port = Number(detail.id);
                                                setSelectedPort(port);
                                                openPort(port);
                                            }}
                                        />
                                    )}
                                </SpaceBetween>
                            ),
                            isOptional: true,
                        },
                    ]}
                />
            )}

            {run.status !== 'running' && (
                <SpaceBetween size="s">
                    <Box />
                    <Alert type="info">Waiting for the run to start.</Alert>
                </SpaceBetween>
            )}
        </Container>
    );
};
