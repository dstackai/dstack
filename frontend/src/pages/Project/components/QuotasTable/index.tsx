import React from 'react';
import { product } from 'product';

import { Alert, Button, Header, InfoLink, Spinner, Table } from 'components';

import { DISCORD_URL } from 'consts';
import { useHelpPanel } from 'hooks';
import { useGetBackendQuotasQuery } from 'services/backendQuota';

const QUOTA_INFO = {
    header: <h2>Quotas</h2>,
    body: (
        <>
            <p>
                These quotas apply per project to the backend with type <code>dstack</code> and are shared across its GPU
                marketplace providers using {product.isSky ? 'Sky' : 'dstack Factory'} billing.
            </p>
            <p>
                Each instance counts toward the quota by the CPU count shown in its offer. This count varies by instance type
                and backend.
            </p>
            <p>Backends connected to your own cloud accounts use your cloud provider's quotas.</p>
            <p>
                To request an increase, ask in <code>#help</code> on{' '}
                <a href={DISCORD_URL} target="_blank" rel="noopener noreferrer">
                    Discord
                </a>
                .
            </p>
        </>
    ),
};

export const QuotasTable: React.FC<{ projectName: string }> = ({ projectName }) => {
    const [openHelpPanel] = useHelpPanel();
    const { currentData: quotas, isFetching, error } = useGetBackendQuotasQuery({ projectName, backendName: 'dstack' });
    const items = [
        { name: 'cpu', value: quotas ? (quotas.find((quota) => quota.name === 'cpu')?.value ?? null) : undefined },
        ...(quotas?.filter((quota) => quota.name !== 'cpu') ?? []),
    ];

    return (
        <div id="project-quotas">
            <Table
                header={
                    <Header
                        variant="h2"
                        info={<InfoLink ariaLabel="Quota information" onFollow={() => openHelpPanel(QUOTA_INFO)} />}
                        actions={
                            <Button
                                href={DISCORD_URL}
                                target="_blank"
                                iconName="external"
                                ariaLabel="Request quota increase on Discord"
                            >
                                Increase
                            </Button>
                        }
                    >
                        Quotas
                    </Header>
                }
                columnDefinitions={[
                    { id: 'type', header: 'Type', cell: (item) => (item.name === 'cpu' ? 'vCPUs' : item.name) },
                    {
                        id: 'value',
                        header: 'Value',
                        cell: (item) =>
                            isFetching && !quotas ? (
                                <Spinner />
                            ) : item.value === undefined ? (
                                '—'
                            ) : item.value === null ? (
                                'No limit'
                            ) : (
                                item.value.toLocaleString()
                            ),
                    },
                ]}
                items={items}
                footer={error ? <Alert type="error">Unable to load quotas.</Alert> : undefined}
            />
        </div>
    );
};
