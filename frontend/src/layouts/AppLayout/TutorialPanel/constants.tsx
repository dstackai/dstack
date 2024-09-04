// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from 'react';

import { AnnotationContextProps, TutorialPanelProps } from 'components';
import { Box } from 'components';

export const tutorialPanelI18nStrings: TutorialPanelProps.I18nStrings = {
    labelsTaskStatus: { pending: 'Pending', 'in-progress': 'In progress', success: 'Success' },
    loadingText: 'Loading',
    tutorialListTitle: 'Take a tour',
    tutorialListDescription: 'Follow the tutorials below to get up to speed with dstack Sky.',
    tutorialListDownloadLinkText: 'Download PDF version',
    tutorialCompletedText: 'Completed',
    labelExitTutorial: 'dismiss tutorial',
    learnMoreLinkText: 'Learn more',
    startTutorialButtonText: 'Start',
    restartTutorialButtonText: 'Restart',
    completionScreenTitle: 'Congratulations! You completed it.',
    feedbackLinkText: 'Feedback',
    dismissTutorialButtonText: 'Dismiss',
    taskTitle: (taskIndex, taskTitle) => `Task ${taskIndex + 1}: ${taskTitle}`,
    stepTitle: (stepIndex, stepTitle) => `Step ${stepIndex + 1}: ${stepTitle}`,
    labelTotalSteps: (totalStepCount) => `Total steps: ${totalStepCount}`,
    labelLearnMoreExternalIcon: 'Opens in a new tab',
    labelTutorialListDownloadLink: 'Download PDF version of this tutorial',
    labelLearnMoreLink: 'Learn more about transcribe audio (opens new tab)',
};

export const overlayI18nStrings: AnnotationContextProps.I18nStrings = {
    stepCounterText: (stepIndex, totalStepCount) => `Step ${stepIndex + 1}/${totalStepCount}`,
    taskTitle: (taskIndex, taskTitle) => `Task ${taskIndex + 1}: ${taskTitle}`,
    labelHotspot: (openState, stepIndex, totalStepCount) =>
        openState
            ? `close annotation for step ${stepIndex + 1} of ${totalStepCount}`
            : `open annotation for step ${stepIndex + 1} of ${totalStepCount}`,
    nextButtonText: 'Next',
    previousButtonText: 'Previous',
    finishButtonText: 'Finish',
    labelDismissAnnotation: 'hide annotation',
};

export enum HotspotIds {
    ADD_TOP_UP_BALANCE = 'billing-top-up-balance',
    PAYMENT_CONTINUE_BUTTON = 'billing-payment-continue-button',
    CONFIGURE_CLI_COMMAND = 'configure-cli-command',
}

export const BILLING_TUTORIAL: TutorialPanelProps.Tutorial = {
    completed: false,
    title: 'Set up billing',
    description: (
        <>
            <Box variant="p" color="text-body-secondary" padding={{ top: 'n' }}>
                Top up your balance via a credit card to use GPU by dstack Sky.
            </Box>
        </>
    ),
    completedScreenDescription: 'TBA',
    tasks: [
        {
            title: 'Add payment method',
            steps: [
                {
                    title: 'Click Top up balance button',
                    content: 'Click Top up balance button',
                    hotspotId: HotspotIds.ADD_TOP_UP_BALANCE,
                },
                {
                    title: 'Click continue',
                    content: 'Please, click continue',
                    hotspotId: HotspotIds.PAYMENT_CONTINUE_BUTTON,
                },
            ],
        },
    ],
};

export const CONFIGURE_CLI_TUTORIAL: TutorialPanelProps.Tutorial = {
    completed: false,
    title: 'Set up the CLI',
    description: (
        <>
            <Box variant="p" color="text-body-secondary" padding={{ top: 'n' }}>
                Configure the CLI on your local machine to submit workload to dstack Sky.
            </Box>
        </>
    ),
    completedScreenDescription: 'TBA',
    tasks: [
        {
            title: 'Configure the CLI',
            steps: [
                {
                    title: 'Run the dstack config command',
                    content: 'Run this command on your local machine to configure the dstack CLI.',
                    hotspotId: HotspotIds.CONFIGURE_CLI_COMMAND,
                },
            ],
        },
    ],
};

export const JOIN_DISCORD_TUTORIAL: TutorialPanelProps.Tutorial = {
    completed: false,
    title: 'Community',
    description: (
        <>
            <Box variant="p" color="text-body-secondary" padding={{ top: 'n' }}>
                Need help or want to chat with other users of dstack? Join our Discord server!
            </Box>
        </>
    ),
    completedScreenDescription: 'TBA',
    tasks: [],
};

export const QUICKSTART_TUTORIAL: TutorialPanelProps.Tutorial = {
    completed: false,
    title: 'Quickstart',
    description: (
        <>
            <Box variant="p" color="text-body-secondary" padding={{ top: 'n' }}>
                Check out the quickstart guide to get started with dstack
            </Box>
        </>
    ),
    completedScreenDescription: 'TBA',
    tasks: [],
};

export const CREDITS_TUTORIAL: TutorialPanelProps.Tutorial = {
    completed: false,
    title: 'Get free credits',
    description: (
        <>
            <Box variant="p" color="text-body-secondary" padding={{ top: 'n' }}>
                Tell us about your project and get some free credits to try dstack Sky!
            </Box>
        </>
    ),
    completedScreenDescription: 'TBA',
    tasks: [],
};
