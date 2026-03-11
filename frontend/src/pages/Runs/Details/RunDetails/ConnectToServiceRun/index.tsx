import React, { FC } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, Box, Button, ExpandableSection, Link, Popover, SpaceBetween, StatusIndicator, Wizard } from 'components';

import { copyToClipboard } from 'libs';
import { getRunProbeStatuses } from 'libs/run';

import { getRunListItemServiceUrl } from '../../../List/helpers';

export const ConnectToServiceRun: FC<{ run: IRun }> = ({ run }) => {
    const { t } = useTranslation();
    const [isExpandedEndpointSection, setIsExpandedEndpointSection] = React.useState(true);
    const [activeStepIndex, setActiveStepIndex] = React.useState(0);
    const serviceUrl = getRunListItemServiceUrl(run);
    const probeStatuses = getRunProbeStatuses(run);
    const hasProbes = probeStatuses.length > 0;
    const allProbesReady = hasProbes && probeStatuses.every((s) => s === 'success');
    const serviceReady = run.status === 'running' && (!hasProbes || allProbesReady) && serviceUrl;

    return (
        <ExpandableSection
            variant="container"
            headerText="Connect"
            expanded={isExpandedEndpointSection}
            onChange={({ detail }) => setIsExpandedEndpointSection(detail.expanded)}
        >
            {run.status !== 'running' && (
                <SpaceBetween size="s">
                    <Box />
                    <Alert type="info">Waiting for the service to start.</Alert>
                </SpaceBetween>
            )}

            {run.status === 'running' && !serviceReady && (
                <SpaceBetween size="s">
                    <Box />
                    <Alert type="info">Waiting for the service to become ready.</Alert>
                </SpaceBetween>
            )}

            {serviceReady && (
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
                    onSubmit={() => setIsExpandedEndpointSection(false)}
                    submitButtonText="Done"
                    allowSkipTo
                    steps={[
                        {
                            title: 'Open',
                            description: 'Open the service endpoint.',
                            content: (
                                <SpaceBetween size="s">
                                    <Alert
                                        type="info"
                                        action={
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
                                                    onClick={() => copyToClipboard(serviceUrl)}
                                                />
                                            </Popover>
                                        }
                                    >
                                        The service is ready at{' '}
                                        <Link href={serviceUrl} external>
                                            {serviceUrl}
                                        </Link>
                                    </Alert>
                                </SpaceBetween>
                            ),
                            isOptional: true,
                        },
                    ]}
                />
            )}
        </ExpandableSection>
    );
};
