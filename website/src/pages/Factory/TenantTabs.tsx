import { CapList } from '../../components/Capabilities';
import { ContentTabs } from '../../components/ContentTabs';
import { billingCapability, exportsCapability, projectsCapability } from './capabilities';

export function TenantTabs() {
  return (
    <ContentTabs
      ariaLabel="Metering and billing"
      className="gs-box--compute-sources"
      tabs={[
        {
          id: 'usage-and-billing',
          label: 'Metering and billing',
          content: <CapList items={[projectsCapability, exportsCapability, billingCapability]} />,
        },
      ]}
    />
  );
}
