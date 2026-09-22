import { CapList, CloudGlyph, KubernetesGlyph, ServerGlyph } from '../pages/Home/GetStartedSection';
import { ContentTabs } from './ContentTabs';

const cloudGroups = [
  ['AWS', 'GCP', 'Azure', 'OCI', 'DigitalOcean', 'Vultr'],
  ['Nebius', 'Crusoe', 'Lambda', 'Verda', 'Runpod'],
  ['AMD Dev Cloud', 'Hot Aisle', 'Vast.ai', 'JarvisLabs'],
];

const onPremItems = [
  { icon: <ServerGlyph />, title: 'SSH fleets', sub: 'Connect VMs or bare-metal clusters over SSH' },
  { icon: <KubernetesGlyph />, title: 'Kubernetes', sub: 'Connect your existing Kubernetes clusters' },
];

export function OnPremCapabilities() {
  return <CapList items={onPremItems} />;
}

export function ComputeSourcesTabs({ cloudsFirst = false }: {
  cloudsFirst?: boolean;
}) {
  const cloudsTab = {
    id: 'clouds',
    label: 'Clouds',
    content: (
      <div className="gs-cloudcols">
        {cloudGroups.map(group => (
          <ul key={group[0]}>
            {group.map(cloud => (
              <li key={cloud} className="gs-cloud">
                <span className="gs-li__ic"><CloudGlyph /></span>
                <span>{cloud}</span>
              </li>
            ))}
          </ul>
        ))}
      </div>
    ),
    footer: (
      <span className="gs-foot__note">
        Configure credentials for your clouds to automate provisioning
      </span>
    ),
  };
  const onPremTab = {
    id: 'onprem',
    label: 'On-prem',
    content: <OnPremCapabilities />,
    footer: (
      <span className="gs-foot__note">
        Use your existing Kubernetes clusters, VMs, or bare-metal clusters
      </span>
    ),
  };

  return (
    <ContentTabs
      ariaLabel="Bring your own compute"
      className="gs-box--compute-sources"
      tabs={cloudsFirst ? [cloudsTab, onPremTab] : [onPremTab, cloudsTab]}
    />
  );
}
