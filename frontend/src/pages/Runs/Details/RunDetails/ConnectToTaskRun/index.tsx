import React, { FC } from 'react';
import { useTranslation } from 'react-i18next';

import {
    Alert,
    Box,
    Button,
    Code,
    ExpandableSection,
    Link,
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

const getMappedPort = (spec: IAppSpec): number | undefined => spec.map_to_port;

export const ConnectToTaskRun: FC<{ run: IRun }> = ({ run }) => {
    const { t } = useTranslation();
    const [isExpandedConnectSection, setIsExpandedConnectSection] = React.useState(true);

    const attachCommand = `dstack attach ${run.run_spec.run_name} --logs`;
    const appSpecs = run.jobs[0]?.job_spec?.app_specs ?? [];
    const mappedAppSpecs = appSpecs.filter((spec) => getMappedPort(spec) != null);

    const [activeStepIndex, setActiveStepIndex] = React.useState(0);
    const [configCliCommand, copyCliCommand] = useConfigProjectCliCommand({ projectName: run.project_name });

    return (
        <ExpandableSection
            variant="container"
            headerText="Connect"
            expanded={isExpandedConnectSection}
            onChange={({ detail }) => setIsExpandedConnectSection(detail.expanded)}
            headerActions={
                <Button
                    iconName="script"
                    variant={isExpandedConnectSection ? 'normal' : 'primary'}
                    onClick={() => setIsExpandedConnectSection((prev) => !prev)}
                />
            }
        >
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
                    onSubmit={() => setIsExpandedConnectSection(false)}
                    submitButtonText="Done"
                    allowSkipTo
                    steps={[
                        {
                            title: 'Attach',
                            description: 'To access this run, first you need to attach to it.',
                            content: (
                                <SpaceBetween size="s">
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
                        ...(mappedAppSpecs.length > 0
                            ? [
                                  {
                                      title: 'Open',
                                      description: 'After the CLI is attached, use the forwarded localhost URLs.',
                                      content: (
                                          <SpaceBetween size="s">
                                              {mappedAppSpecs.map((spec) => {
                                                  const mappedPort = getMappedPort(spec)!;
                                                  const localUrl = `http://127.0.0.1:${mappedPort}`;

                                                  return (
                                                      <Alert
                                                          key={`${spec.port}-${mappedPort}`}
                                                          type="info"
                                                          action={
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
                                                                      onClick={() => copyToClipboard(localUrl)}
                                                                  />
                                                              </Popover>
                                                          }
                                                      >
                                                          Port {spec.port} is forwarded to{' '}
                                                          <Link href={localUrl} external>
                                                              {localUrl}
                                                          </Link>
                                                      </Alert>
                                                  );
                                              })}
                                          </SpaceBetween>
                                      ),
                                      isOptional: true,
                                  },
                              ]
                            : []),
                    ]}
                />
            )}

            {run.status !== 'running' && (
                <SpaceBetween size="s">
                    <Box />
                    <Alert type="info">Waiting for the run to start.</Alert>
                </SpaceBetween>
            )}
        </ExpandableSection>
    );
};
