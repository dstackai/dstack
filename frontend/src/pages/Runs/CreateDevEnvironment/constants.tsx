import React from 'react';

import { IRunEnvironmentFormKeys } from './types';
export const CONFIG_INFO = {
    header: <h2>Credits history</h2>,
    body: (
        <>
            <p>Available for only the global admin role</p>
        </>
    ),
};

export const FORM_FIELD_NAMES = {
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
} as const satisfies Record<IRunEnvironmentFormKeys, IRunEnvironmentFormKeys>;
