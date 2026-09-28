import { LayersGlyph } from '../../components/Capabilities';
import { BillingGlyph, ExportGlyph, MeteringGlyph, MetricsGlyph, PresetGlyph, ProjectGlyph } from '../../components/ConceptIcons';

export const eventsCapability = {
  icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 6h13M8 12h13M8 18h13" />
      <path d="M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  ),
  title: 'Events',
  sub: 'Audit user actions and resource lifecycle events across projects.',
};

export const metricsCapability = {
  icon: <MetricsGlyph />,
  title: 'Metrics',
  sub: 'Monitor utilization, accelerator health, and network health',
};

export const projectsCapability = {
  icon: <ProjectGlyph />,
  title: 'Projects',
  sub: 'Tenant isolation and resource access control',
};

export const exportsCapability = {
  icon: <ExportGlyph />,
  title: 'Exports',
  sub: 'Share selected fleets and gateways across projects',
};

export const meteringCapability = {
  icon: <MeteringGlyph />,
  title: 'Metering',
  sub: 'Track compute, storage, and token usage per tenant',
};

export const billingCapability = {
  icon: <BillingGlyph />,
  title: 'Billing',
  sub: 'Automate customer charges, balances, and payments',
};

export const presetsCapability = {
  icon: <PresetGlyph />,
  title: 'Presets',
  sub: 'Agent-based optimization and kernel generation',
};

export const registryCapability = {
  icon: <LayersGlyph />,
  title: 'Registry',
  sub: 'Day-0 optimized presets for frontier open models',
};
