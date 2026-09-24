import { BoxGlyph, LayersGlyph } from '../../components/Capabilities';

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
  icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 3v18h18M7 14l4-4 4 3 6-8" />
    </svg>
  ),
  title: 'Metrics',
  sub: 'Monitor utilization, accelerator health, and network health',
};

export const projectsCapability = {
  icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      <circle cx="9" cy="7" r="4" />
    </svg>
  ),
  title: 'Projects',
  sub: 'Tenant isolation and resource access control',
};

export const exportsCapability = {
  icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      <path d="m8.59 10.49 6.82-3.98m-6.82 6.98 6.82 3.98" />
    </svg>
  ),
  title: 'Exports',
  sub: 'Share selected fleets and gateways across projects',
};

export const billingCapability = {
  icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="M2 10h20M6 15h4" />
    </svg>
  ),
  title: 'Billing',
  sub: 'Compute and token metering and billing automation',
};

export const presetsCapability = {
  icon: <BoxGlyph />,
  title: 'Presets',
  sub: 'Agent-based optimization and kernel generation',
};

export const registryCapability = {
  icon: <LayersGlyph />,
  title: 'Registry',
  sub: 'Day-0 optimized presets for frontier open models',
};
