import { CapList } from '../../components/Capabilities';
import { OnPremCapabilities } from '../../components/ComputeSourcesTabs';
import { ContentTabs } from '../../components/ContentTabs';
import { eventsCapability, metricsCapability } from './capabilities';

export function CapacityTabs() {
  return (
    <ContentTabs
      ariaLabel="A unified control plane"
      className="gs-box--compute-sources"
      tabs={[
        {
          id: 'management',
          label: 'Capacity management',
          content: <OnPremCapabilities />,
        },
        {
          id: 'observability',
          label: 'Observability',
          content: <CapList items={[eventsCapability, metricsCapability]} />,
        },
      ]}
    />
  );
}
