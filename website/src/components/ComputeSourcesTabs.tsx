import { KeyboardEvent, useId, useRef, useState } from 'react';
import { CapList, CloudGlyph, KubernetesGlyph, ServerGlyph } from '../pages/Home/GetStartedSection';

const cloudGroups = [
  ['AWS', 'GCP', 'Azure', 'OCI', 'DigitalOcean', 'Vultr'],
  ['Nebius', 'Crusoe', 'Lambda', 'Verda', 'Runpod'],
  ['AMD Dev Cloud', 'Hot Aisle', 'Vast.ai', 'JarvisLabs'],
];

const onPremItems = [
  { icon: <ServerGlyph />, title: 'SSH fleets', sub: 'Attach bare-metal servers or VMs with SSH access' },
  { icon: <KubernetesGlyph />, title: 'Kubernetes', sub: 'Attach your existing Kubernetes clusters' },
];

type ComputeTab = 'clouds' | 'onprem';

export function ComputeSourcesTabs({ cloudsFirst = false }: {
  cloudsFirst?: boolean;
}) {
  const tabs: ComputeTab[] = cloudsFirst ? ['clouds', 'onprem'] : ['onprem', 'clouds'];
  const [pane, setPane] = useState<ComputeTab>(tabs[0]);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useId();

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const nextIndex = {
      ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index + tabs.length - 1) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    }[event.key];
    if (nextIndex === undefined) return;
    event.preventDefault();
    setPane(tabs[nextIndex]);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <div className="gs-box gs-box--compute-sources">
      <div className="gs-tabs" role="tablist" aria-label="Bring your own compute">
        {tabs.map((tab, index) => (
          <button
            key={tab}
            ref={element => { tabRefs.current[index] = element; }}
            id={`${id}-${tab}`}
            type="button"
            role="tab"
            aria-selected={pane === tab}
            aria-controls={`${id}-panel`}
            tabIndex={pane === tab ? 0 : -1}
            className={`gs-tab${pane === tab ? ' gs-tab--on' : ''}`}
            onClick={() => setPane(tab)}
            onKeyDown={event => onTabKeyDown(event, index)}
          >
            {tab === 'clouds' ? 'Clouds' : 'On-prem'}
          </button>
        ))}
      </div>
      <div
        className="gs-skybody"
        id={`${id}-panel`}
        role="tabpanel"
        aria-labelledby={`${id}-${pane}`}
        tabIndex={0}
      >
        {pane === 'onprem' && <CapList items={onPremItems} />}
        {pane === 'clouds' && (
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
        )}
      </div>
      <div className="gs-boxfoot">
        <span className="gs-foot__note">
          {pane === 'clouds'
            ? 'Configure credentials for your clouds to automate provisioning'
            : 'Bring bare-metal servers, a Kubernetes cluster, or just VMs'}
        </span>
      </div>
    </div>
  );
}
