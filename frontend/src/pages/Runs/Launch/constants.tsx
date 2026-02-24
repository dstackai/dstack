import React from 'react';
import Link from '@cloudscape-design/components/link';

import { IRunEnvironmentFormKeys } from './types';
export const CONFIGURATION_INFO = {
    header: <h2>Configuration</h2>,
    body: (
        <>
            <p>
                This is the <code>dstack</code> run configuration generated from the template and your settings. You
                can review and adjust it before launching.
            </p>

            <p>To learn more, see:</p>

            <ul>
                <li>
                    <Link href="https://dstack.ai/docs/concepts/dev-environments" external>
                        Dev environments
                    </Link>
                </li>
                <li>
                    <Link href="https://dstack.ai/docs/concepts/tasks" external>
                        Tasks
                    </Link>
                </li>
                <li>
                    <Link href="https://dstack.ai/docs/concepts/services" external>
                        Services
                    </Link>
                </li>
            </ul>
        </>
    ),
};

export const PASSWORD_INFO = {
    header: <h2>Password</h2>,
    body: (
        <>
            <p>
                A random password has been generated for this run. You will need it to access the run once it is
                launched.
            </p>

            <p>Make sure to copy the password before proceeding. Only share it with those you want to give access to.</p>
        </>
    ),
};

export const FORM_FIELD_NAMES = {
    project: 'project',
    template: 'template',
    gpu_enabled: 'gpu_enabled',
    offer: 'offer',
    name: 'name',
    ide: 'ide',
    config_yaml: 'config_yaml',
    docker: 'docker',
    image: 'image',
    python: 'python',
    repo_enabled: 'repo_enabled',
    repo_url: 'repo_url',
    repo_path: 'repo_path',
    working_dir: 'working_dir',
    password: 'password',
    password_copied: 'password_copied',
} as const satisfies Record<IRunEnvironmentFormKeys, IRunEnvironmentFormKeys>;

export const IDE_OPTIONS = [
    {
        label: 'Cursor',
        value: 'cursor',
    },
    {
        label: 'VS Code',
        value: 'vscode',
    },
    {
        label: 'Windsurf',
        value: 'windsurf',
    },
] as const;

export const IDE_DISPLAY_NAMES: Record<string, string> = {
    cursor: 'Cursor',
    vscode: 'VS Code',
    windsurf: 'Windsurf',
};

export const getIDEDisplayName = (ide: string): string => {
    return IDE_DISPLAY_NAMES[ide] || 'IDE';
};
