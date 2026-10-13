import React from 'react';

import { Link, NavigateLink } from 'components';

import { DOCS_URL, QUICK_START_URL } from 'consts';
import { ROUTES } from 'routes';

export const CLI_INFO = {
    header: <h2>Run with the CLI</h2>,
    body: (
        <>
            <p>
                A run is described by a configuration in a <code>.dstack.yml</code> file and submitted with{' '}
                <code>dstack apply</code>.
            </p>
            <ul>
                <li>
                    <Link href={`${DOCS_URL}concepts/dev-environments/`} external>
                        Dev environments
                    </Link>{' '}
                    let you provision an instance and access it with your desktop IDE or SSH.
                </li>
                <li>
                    <Link href={`${DOCS_URL}concepts/tasks/`} external>
                        Tasks
                    </Link>{' '}
                    run arbitrary commands on one or more nodes, such as training or batch processing.
                </li>
                <li>
                    <Link href={`${DOCS_URL}concepts/services/`} external>
                        Services
                    </Link>{' '}
                    deploy models or web apps as secure and scalable endpoints.
                </li>
            </ul>
            <p>
                For a step-by-step walkthrough, see the{' '}
                <Link href={QUICK_START_URL} external>
                    Quickstart
                </Link>
                .
            </p>
        </>
    ),
};

export const getTemplatesInfo = (projectName: string) => ({
    header: <h2>From a template</h2>,
    body: (
        <>
            <p>
                A template is a run configuration with a form. Pick a template, choose resources, and fill in its settings; the
                last step shows the resulting configuration before you launch it.
            </p>
            <p>
                Templates come from a Git repository: each is a YAML file in its <code>.dstack/templates</code> folder. A
                project admin sets the repository in the{' '}
                <NavigateLink href={`${ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(projectName)}#danger-zone`}>
                    project settings
                </NavigateLink>
                ; without one, the server&apos;s default is used.
            </p>
            <p>
                See examples in{' '}
                <Link href="https://github.com/dstackai/dstack-templates" external>
                    dstackai/dstack-templates
                </Link>
                .
            </p>
        </>
    ),
});

export const AGENTS_INFO = {
    header: <h2>Run with agents</h2>,
    body: (
        <>
            <p>
                With{' '}
                <Link href="https://skills.sh/dstackai/dstack/dstack" external>
                    dstack skills
                </Link>{' '}
                installed, AI agents like Claude, Codex, and Cursor work with dstack on your behalf: they define configurations,
                run them, and manage dstack through the CLI, from fleets and volumes to runs and their logs.
            </p>
            <p>
                See{' '}
                <Link href={`${DOCS_URL}installation/#skills`} external>
                    Installation
                </Link>{' '}
                for details.
            </p>
        </>
    ),
};
