import React from 'react';
import { ButtonAppearance } from 'components/Button';
import { ReactComponent as InfinityIcon } from 'assets/icons/landing/infinity.svg';
import { ReactComponent as CrownIcon } from 'assets/icons/landing/crown.svg';
import { ReactComponent as CheckIcon } from 'assets/icons/check.svg';
import * as routes from 'routes';
import { goToUrl } from 'libs';

export const tools = [
    {
        title: 'Git-focused',
        text:
            'Define workflows and their hardware requirements as code.\n' +
            'dstack tracks the code automatically.',
    },
    {
        title: 'Data management',
        text:
            'Workflow artifacts are the 1st-class citizens.\n' +
            'Assign tags to finished workflows to reuse their artifacts.',
    },
    {
        title: 'Environment setup',
        text: 'No need to build custom Docker images or setup CUDA yourself.\n' + 'Just specify Conda requirements.',
    },
    {
        title: 'Interruption-friendly',
        text:
            'You can fully-leverage interruptible (spot/preemptive) instances and resume workflows from where they ' +
            'were interrupted.',
    },
    {
        title: 'Technology agnostic',
        text: 'No need to use specific APIs in your code.\nAnything that works locally, can run via dstack.',
    },
    {
        title: 'Dev environments',
        text: 'Workflows may be not only tasks or applications but also dev environments, including IDEs, notebooks, etc.',
    },
    {
        title: 'Very easy setup',
        text:
            'Install the dstack CLI and run workflows in the cloud using your local credentials.\n' +
            'No need to set up anything else.',
    },
];

export const providers = [
    {
        name: 'bash',
        description: 'Runs shell commands',
        url: 'https://docs.dstack.ai/providers/bash',
    },
    {
        name: 'python',
        description: 'Runs a Python script',
        url: 'https://docs.dstack.ai/providers/python',
    },
    {
        name: 'tensorboard',
        description: 'Runs a Tensorboard script',
        url: 'https://docs.dstack.ai/providers/tensorboard',
    },
    {
        name: 'notebook',
        description: 'Launches a Jupyter app',
        url: 'https://docs.dstack.ai/providers/lab',
    },
    {
        name: 'lab',
        description: 'Launches a JupyterLab app',
        url: 'https://docs.dstack.ai/providers/lab',
    },
    {
        name: 'code',
        description: 'Launches a VS Code app',
        url: 'https://docs.dstack.ai/providers/code',
    },
    {
        name: 'streamlit',
        description: 'Launches a Streamlit app',
        url: 'https://docs.dstack.ai/providers/streamlit',
    },
    {
        name: 'gradio',
        description: 'Launches a Gradio app',
        url: 'https://docs.dstack.ai/providers/gradio',
    },
    {
        name: 'fastapi',
        description: 'Launches a FastAPI app',
        url: 'https://docs.dstack.ai/providers/fastapi',
    },
    {
        name: 'docker',
        description: 'Run a Docker image',
        url: 'https://docs.dstack.ai/providers/docker',
    },
    {
        name: 'torchrun',
        description: 'Runs a distributed training',
        url: 'https://docs.dstack.ai/providers/torchrun',
    },
    /*{
        name: 'curl',
        description: 'This provider downloads a file from a given URL and saves it as an output artifact.',
        url: 'https://docs.dstack.ai/providers/curl',
        tags: ['data',],
    },*/
];

export const plans: {
    name: string;
    title: string;
    description: string;
    price?: string;
    opportunities: string[];
    info?: string;
    command?: string;
    button: {
        action: () => void;
        appearance: ButtonAppearance;
        title: string;
    };
    props: {
        value: string | React.ReactNode;
        text: string;
    }[];
}[] = [
    {
        name: 'free',
        title: 'Free',
        description: 'For individuals and small teams',
        opportunities: ['Hosted by dstack'],
        price: '',
        info: 'No credit card is required',
        button: {
            action: () => goToUrl(routes.signUp()),
            appearance: 'blue-fill',
            title: 'Sign up for free',
        },
        props: [
            {
                value: <CheckIcon width={29} height={10} />,
                text: 'Link your AWS, GCP or Azure account',
            },
            {
                value: '1',
                text: 'Private repo',
            },
            {
                value: '1TB',
                text: 'Artifact storage',
            },
        ],
    },

    {
        name: 'team',
        title: 'Team',
        description: 'For larger teams and organizations',
        opportunities: ['Hosted by dstack'],
        price: '$20/user',
        button: {
            action: () => {
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-ignore
                Tally.openPopup('3XZdjn', {
                    layout: 'modal',
                    width: 800,
                    hideTitle: true,
                });
            },
            appearance: 'black-stroke',
            title: 'Contact us',
        },
        props: [
            {
                value: <CheckIcon width={29} height={10} />,
                text: 'Link your AWS, GCP or Azure account',
            },
            {
                value: <InfinityIcon width={29} />,
                text: 'Unlimited private repos',
            },
            {
                value: <InfinityIcon width={29} />,
                text: 'Unlimited artifact storage',
            },
            /*{
                value: <CrownIcon width={29} />,
                text: 'Use own K8S cluster',
            },*/
            /*{
                value: <CrownIcon width={29} />,
                text: 'On-premise installation',
            },*/
            /*{
                value: <CrownIcon width={29} />,
                text: 'Advanced compliance',
            },*/
            {
                // value: <CrownIcon width={29} />,
                value: <InfinityIcon width={29} height={10} />,
                text: 'Unlimited collaborators',
            },
        ],
    },
];
