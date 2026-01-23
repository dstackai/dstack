import React from 'react';

export const DEFAULT_FLEET_INFO = {
    header: <h2>Default fleet</h2>,
    body: (
        <>
            <p>
                Fleets act both as pools of instances and as templates for how those instances are provisioned. When you submit
                a dev environment, task, or service, <code>dstack</code> reuses <code>idle</code> instances or provisions new
                ones based on the fleet configuration.
            </p>

            <p>
                If you set <code>Min number of instances</code> to <code>0</code>, <code>dstack</code> will provision instances
                only when you run a dev environment, task, or service.
            </p>

            <p>
                At least one fleet is required to run dev environments, tasks, or services. Create it here, or create it using
                the <code>dstack apply</code> command via the CLI.
            </p>

            <p>
                To learn more about fleets, see the{' '}
                <a href={'https://dstack.ai/docs/concepts/fleets'} target="_blank">
                    documentation
                </a>
                .
            </p>
        </>
    ),
};
