import { CapList, CloudGlyph, KubernetesGlyph, ServerGlyph, SlurmGlyph } from './Capabilities';
import { ContentTabs } from './ContentTabs';
import { ViewDocsButton } from './ViewDocsButton';
import { docsUrl } from '../routes';

const cloudGroups = [
  [
    { name: 'AWS', anchor: 'aws' },
    { name: 'GCP', anchor: 'gcp' },
    { name: 'Azure', anchor: 'azure' },
    { name: 'OCI', anchor: 'oci' },
    { name: 'DigitalOcean', anchor: 'digital-ocean' },
    { name: 'Vultr', anchor: 'vultr' },
  ],
  [
    { name: 'Nebius', anchor: 'nebius' },
    { name: 'Crusoe', anchor: 'crusoe' },
    { name: 'Lambda', anchor: 'lambda' },
    { name: 'Verda', anchor: 'verda' },
    { name: 'Runpod', anchor: 'runpod' },
  ],
  [
    { name: 'AMD Dev Cloud', anchor: 'amd-developer-cloud' },
    { name: 'Hot Aisle', anchor: 'hot-aisle' },
    { name: 'Vast.ai', anchor: 'vastai' },
    { name: 'JarvisLabs', anchor: 'jarvislabs' },
  ],
];

const onPremItems = [
  { icon: <ServerGlyph />, title: 'SSH fleets', sub: 'Connect VMs or bare-metal clusters over SSH', href: docsUrl('concepts/fleets/#ssh-fleets') },
  { icon: <KubernetesGlyph />, title: 'Kubernetes', sub: 'Connect your existing Kubernetes clusters', href: docsUrl('concepts/backends/#kubernetes') },
  { icon: <SlurmGlyph />, title: 'Slurm', sub: 'Connect your existing Slurm clusters (experimental)', href: docsUrl('concepts/backends/#slurm') },
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
          <ul key={group[0].name}>
            {group.map(cloud => (
              <li key={cloud.name}>
                <a className="gs-cloud" href={docsUrl(`concepts/backends/#${cloud.anchor}`)}>
                  <span className="gs-li__ic"><CloudGlyph /></span>
                  <span>{cloud.name}</span>
                </a>
              </li>
            ))}
          </ul>
        ))}
      </div>
    ),
    footer: (
      <>
        <span className="gs-foot__note">
          Configure credentials for your clouds to automate provisioning
        </span>
        <ViewDocsButton href={docsUrl('concepts/backends/')} />
      </>
    ),
  };
  const onPremTab = {
    id: 'onprem',
    label: 'On-prem',
    content: <OnPremCapabilities />,
    footer: (
      <>
        <span className="gs-foot__note">
          Use your existing Kubernetes or Slurm clusters, VMs, or bare-metal
        </span>
        <ViewDocsButton href={docsUrl('concepts/backends/')} />
      </>
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
