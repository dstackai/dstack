import { ReactNode } from 'react';
import { CapList } from '../../components/Capabilities';
import { ContentTabs } from '../../components/ContentTabs';
import {
  billingCapability,
  eventsCapability,
  exportsCapability,
  registryCapability,
} from './capabilities';

export function FactoryGetStartedTabs({ footer }: { footer?: ReactNode }) {
  return (
    <ContentTabs
      ariaLabel="dstack Factory capabilities"
      className="gs-box--compute-sources"
      tabs={[
        {
          id: 'resource-sharing',
          label: 'Multi-tenancy',
          content: <CapList items={[exportsCapability, billingCapability]} />,
          footer,
        },
        {
          id: 'observability',
          label: 'Observability',
          content: <CapList items={[eventsCapability]} />,
          footer,
        },
        {
          id: 'optimized-inference',
          label: 'Serverless inference',
          content: <CapList items={[registryCapability]} />,
          footer,
        },
      ]}
    />
  );
}
