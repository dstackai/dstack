import React from 'react';
import Link from '@cloudscape-design/components/link';

export const CLI_INFO = {
    header: <h2>CLI</h2>,
    body: (
        <>
            <p>
                To use this project with your CLI, add it using the
                <a href={'https://dstack.ai/docs/reference/cli/dstack/project/'} target="_blank">
                    <code>dstack project add</code>
                </a>{' '}
                command.
            </p>
            <p>
                To learn how to install the CLI, refer to the{' '}
                <a href={'https://dstack.ai/docs/installation#set-up-the-cli'} target="_blank">
                    installation
                </a>{' '}
                guide.
            </p>
        </>
    ),
};

export const TEMPLATES_REPO_INFO = {
    header: <h2>Templates</h2>,
    body: (
        <>
            <p>
                Specify a project-level templates Git repository URL. Templates from this repo are shown on the Launch page in
                Runs, and setting it enables the Launch button when templates are available.
            </p>
            <p>If set, project templates override global templates configured on the server.</p>
            <p>
                See official examples in{' '}
                <Link href="https://github.com/dstackai/dstack-templates" external>
                    dstackai/dstack-templates
                </Link>
                .
            </p>
        </>
    ),
};
