import { CapList } from '../../components/Capabilities';
import { ContentTabs } from '../../components/ContentTabs';
import { presetsCapability, registryCapability } from './capabilities';

export function InferenceTabs() {
  return (
    <ContentTabs
      ariaLabel="Serverless inference"
      className="gs-box--compute-sources"
      tabs={[
        {
          id: 'inference-optimization',
          label: 'Inference optimization',
          content: <CapList items={[presetsCapability, registryCapability]} />,
        },
      ]}
    />
  );
}
