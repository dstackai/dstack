import { CapList, ServerGlyph } from '../../components/Capabilities';
import { ContentTabs } from '../../components/ContentTabs';

const orchestrationItems = [
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="2" y="4" width="20" height="16" rx="2" />
        <path d="m6 8 4 4-4 4M14 16h4" />
      </svg>
    ),
    title: 'Tasks',
    sub: 'Training and other kinds of batch jobs',
  },
  {
    icon: <ServerGlyph />,
    title: 'Services',
    sub: 'Cache-aware and disaggregated inference',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="9" y="2" width="6" height="6" rx="1" />
        <rect x="2" y="16" width="6" height="6" rx="1" />
        <rect x="16" y="16" width="6" height="6" rx="1" />
        <path d="M12 8v4M5 16v-4h14v4" />
      </svg>
    ),
    title: 'Gateways',
    sub: 'HTTPS, domains, rate limits, and auto-scaling',
  },
];

export function OrchestrationTabs() {
  return (
    <ContentTabs
      ariaLabel="AI-native orchestration"
      className="gs-box--compute-sources"
      tabs={[
        {
          id: 'orchestration',
          label: 'Orchestration',
          content: <CapList items={orchestrationItems} />,
        },
      ]}
    />
  );
}
