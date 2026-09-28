import { CapList } from '../../components/Capabilities';
import { GatewayGlyph, ServiceGlyph, TaskGlyph } from '../../components/ConceptIcons';
import { ContentTabs } from '../../components/ContentTabs';

const orchestrationItems = [
  {
    icon: <TaskGlyph />,
    title: 'Tasks',
    sub: 'Training and other kinds of batch jobs',
  },
  {
    icon: <ServiceGlyph />,
    title: 'Services',
    sub: 'Cache-aware and disaggregated inference',
  },
  {
    icon: <GatewayGlyph />,
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
