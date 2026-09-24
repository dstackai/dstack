import { CapList } from '../../components/Capabilities';
import { ContentTabs } from '../../components/ContentTabs';
import { billingCapability, exportsCapability, projectsCapability } from './capabilities';

export function TenantTabs() {
  return (
    <ContentTabs
      ariaLabel="Multi-tenancy and billing"
      className="gs-box--compute-sources"
      tabs={[
        {
          id: 'usage-and-billing',
          label: 'Usage and billing',
          content: <CapList items={[projectsCapability, exportsCapability, billingCapability]} />,
        },
      ]}
    />
  );
}
