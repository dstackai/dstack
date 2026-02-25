import React, { FC } from 'react';

import { Alert, Box, Container, Header, Link, SpaceBetween } from 'components';

import { getRunProbeStatuses } from 'libs/run';

import { getRunListItemServiceUrl } from '../../../List/helpers';

export const ConnectToServiceRun: FC<{ run: IRun }> = ({ run }) => {
    const serviceUrl = getRunListItemServiceUrl(run);
    const probeStatuses = getRunProbeStatuses(run);
    const hasProbes = probeStatuses.length > 0;
    const allProbesReady = hasProbes && probeStatuses.every((s) => s === 'success');
    const serviceReady = run.status === 'running' && (!hasProbes || allProbesReady) && serviceUrl;

    return (
        <Container>
            <Header variant="h2">Endpoint</Header>

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
                <SpaceBetween size="s">
                    <Box />
                    <Alert type="success">
                        The service is ready at{' '}
                        <Link href={serviceUrl} external>
                            {serviceUrl}
                        </Link>
                    </Alert>
                </SpaceBetween>
            )}
        </Container>
    );
};
