import React, { FC } from 'react';
import { useTranslation } from 'react-i18next';

import {
    Alert,
    Box,
    Button,
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

import styles from './styles.module.scss';

const UvInstallCommand = 'uv tool install dstack -U';
const PipInstallCommand = 'pip install dstack -U';

export const ConnectToRunWithDevEnvConfiguration: FC<{ run: IRun }> = ({ run }) => {
    const { t } = useTranslation();

    const getAttachCommand = (runData: IRun) => {
        const attachCommand = `dstack attach ${runData.run_spec.run_name} --logs`;

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
    const [attachCommand, copyAttachCommand] = getAttachCommand(run);
    const [sshCommand, copySSHCommand] = getSSHCommand(run);

    const openInIDEUrl = `${run.run_spec.configuration.ide}://vscode-remote/ssh-remote+${run.run_spec.run_name}/${run.run_spec.working_dir || 'workflow'}`;

    const [configCliCommand, copyCliCommand] = useConfigProjectCliCommand({ projectName: run.project_name });

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
                    onSubmit={() => window.open(openInIDEUrl, '_blank')}
                    submitButtonText="Open in VS Code"
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

            {run.status !== 'running' && (
                <SpaceBetween size="s">
                    <Box />
                    <Alert type="info">Waiting for the run to start.</Alert>
                </SpaceBetween>
            )}
        </Container>
    );
};
