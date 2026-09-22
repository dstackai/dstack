import { ContentTabs } from '../../components/ContentTabs';
import { BoxGlyph, CapList, LayersGlyph } from '../Home/GetStartedSection';

const inferenceItems = [
  {
    icon: <BoxGlyph />,
    title: 'Presets',
    sub: 'Agent-based optimization and kernel generation',
  },
  {
    icon: <LayersGlyph />,
    title: 'Registry',
    sub: 'Day-0 optimized presets for frontier open models',
  },
];

export function InferenceTabs() {
  return (
    <ContentTabs
      ariaLabel="Serverless inference"
      className="gs-box--compute-sources"
      tabs={[
        {
          id: 'inference-optimization',
          label: 'Inference optimization',
          content: <CapList items={inferenceItems} />,
        },
      ]}
    />
  );
}
