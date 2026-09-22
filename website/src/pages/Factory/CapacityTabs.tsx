import { OnPremCapabilities } from '../../components/ComputeSourcesTabs';
import { ContentTabs } from '../../components/ContentTabs';
import { CapList } from '../Home/GetStartedSection';

const observabilityItems = [
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M8 6h13M8 12h13M8 18h13" />
        <path d="M3 6h.01M3 12h.01M3 18h.01" />
      </svg>
    ),
    title: 'Events',
    sub: 'Track resource state changes and operations',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M3 3v18h18M7 14l4-4 4 3 6-8" />
      </svg>
    ),
    title: 'Metrics',
    sub: 'Monitor utilization, accelerator health, and network health',
  },
];

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
          content: <CapList items={observabilityItems} />,
        },
      ]}
    />
  );
}
