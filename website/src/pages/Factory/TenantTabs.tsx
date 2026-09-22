import { ContentTabs } from '../../components/ContentTabs';
import { CapList } from '../Home/GetStartedSection';

const tenantItems = [
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
        <circle cx="9" cy="7" r="4" />
      </svg>
    ),
    title: 'Projects',
    sub: 'Tenant isolation and resource access control',
  },
  {
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
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="2" y="4" width="20" height="16" rx="2" />
        <path d="M2 10h20M6 15h4" />
      </svg>
    ),
    title: 'Billing',
    sub: 'Usage metering and automated customer billing',
  },
];

export function TenantTabs() {
  return (
    <ContentTabs
      ariaLabel="Multi-tenancy and billing"
      className="gs-box--compute-sources"
      tabs={[
        {
          id: 'usage-and-billing',
          label: 'Usage and billing',
          content: <CapList items={tenantItems} />,
        },
      ]}
    />
  );
}
