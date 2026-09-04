import { useState } from 'react';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';
import { ArchitectureDiagram } from '../../components/ArchitectureDiagram';
import { highlightTerms } from '../../components/highlightTerms';
import { docsUrl } from '../../routes';
import { CapList, CloudGlyph, KubernetesGlyph, ServerGlyph } from './GetStartedSection';

// Core orchestration primitives shown in the "AI-native orchestration" block. "Runs" folds the
// three run types (dev environments, tasks, services) into one card; there's no single runs
// concept page, so it links to the quickstart ("creating fleets and submitting runs").
const keyConcepts = [
  { name: 'Projects', href: docsUrl('concepts/projects'), description: 'Multi-tenancy and resource isolation' },
  { name: 'Fleets', href: docsUrl('concepts/fleets'), description: 'Cluster provisioning and monitoring' },
  { name: 'Runs', href: docsUrl('quickstart'), description: 'Training and inference primitives' },
  { name: 'Presets', href: docsUrl('concepts/presets'), description: 'Agent-based inference optimization' },
  { name: 'Gateways', href: docsUrl('concepts/gateways'), description: 'Ingress, auto-scaling, rate limits, etc' },
];

// The main marketing content: a sequence of alternating documentation blocks.
export function ExploreSection() {
  return (
    <section className="docs-section explore-section" id="explore">
      <AlternatingDocBlock visual={<ArchitectureDiagram />} title="Vendor-agnostic, open-source" imageFirst>
        dstack gives cloud tenants and data-center operators a unified control plane for managing compute and orchestrating AI workloads.
        <br />
        <br />
        It improves operational efficiency and removes vendor lock-in. No more hassle of building your own compute stack on top of Kubernetes or Slurm.
      </AlternatingDocBlock>

      <KeyConceptsBlock />

      <BringComputeBlock />

    </section>
  );
}

// Clouds grid for the merged compute block, grouped per column: traditional hyperscalers,
// top GPU neoclouds, then smaller GPU clouds.
const CLOUD_GROUPS = [
  ['AWS', 'GCP', 'Azure', 'OCI', 'DigitalOcean', 'Vultr'],
  ['Nebius', 'Crusoe', 'Lambda', 'Verda', 'Runpod'],
  ['AMD Dev Cloud', 'Hot Aisle', 'Vast.ai', 'JarvisLabs'],
];

// On-prem capability rows for the merged compute block (same shape as the Factory CapList tabs).
const onPremItems = [
  { icon: <ServerGlyph />, title: 'SSH fleets', sub: 'Attach bare-metal servers or VMs with SSH access' },
  { icon: <KubernetesGlyph />, title: 'Kubernetes', sub: 'Attach your existing Kubernetes clusters' },
];

// One block for both compute targets: the Get-started panes' tabbed box as the visual (on-prem
// rows / the clouds grid), with a footer note that swaps with the selected tab (like the dstack
// Sky pane's notes). The prose beside it is static and condenses the former per-target blocks.
// These are core dstack capabilities, so they live here rather than under dstack Factory.
function BringComputeBlock() {
  const [pane, setPane] = useState<'onprem' | 'clouds'>('onprem');
  return (
    <AlternatingDocBlock
      visual={
        <div className="gs-box">
          <div className="gs-tabs" role="tablist" aria-label="Bring your own compute">
            <button
              type="button"
              role="tab"
              aria-selected={pane === 'onprem'}
              className={`gs-tab${pane === 'onprem' ? ' gs-tab--on' : ''}`}
              onClick={() => setPane('onprem')}
            >
              On-prem
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={pane === 'clouds'}
              className={`gs-tab${pane === 'clouds' ? ' gs-tab--on' : ''}`}
              onClick={() => setPane('clouds')}
            >
              Clouds
            </button>
          </div>
          <div className="gs-skybody">
            {pane === 'onprem' && <CapList items={onPremItems} />}
            {pane === 'clouds' && (
              <div className="gs-cloudcols">
                {CLOUD_GROUPS.map(group => (
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
            {pane === 'onprem' && (
              <span className="gs-foot__note">Bring bare-metal servers, a Kubernetes cluster, or just VMs</span>
            )}
            {pane === 'clouds' && (
              <span className="gs-foot__note">Configure credentials for your clouds to automate provisioning</span>
            )}
          </div>
        </div>
      }
      title="Bring your own compute"
      imageFirst
    >
      Have bare-metal servers or VMs with SSH access? Point dstack to those hosts and provide SSH
      credentials to create an SSH fleet. Have an existing Kubernetes cluster? Point dstack's
      Kubernetes backend to the kubeconfig. dstack will schedule workloads on them alongside cloud
      clusters.
      <br />
      <br />
      dstack natively integrates with the major GPU clouds and automates provisioning of clusters.
      Authorize dstack by configuring backends with your credentials, and dstack will provision fleets
      and schedule workloads in your own cloud account.
    </AlternatingDocBlock>
  );
}

function KeyConceptsBlock() {
  return (
    <AlternatingDocBlock
      visual={
        <div className="concept-grid-wrap">
          <div className="concept-grid">
            {keyConcepts.map(concept => (
              // Whole card is the link so it reads as clickable. Kept as a real <a>
              // (open-in-new-tab / SEO) rather than Cloudscape's onClick-only ActionCard.
              <a className="media-card concept-card" href={concept.href} key={concept.name}>
                <h3>{concept.name}</h3>
                <p>{highlightTerms(concept.description)}</p>
              </a>
            ))}
          </div>
        </div>
      }
      title="AI-native orchestration"
    >
      Managing AI infrastructure requires first-class primitives for compute management, training, inference, and observability that support heterogeneous AI compute.
      <br />
      <br />
      dstack provides a streamlined interface to efficiently utilize cloud compute, run data-center operations, or run your own AI token factory at planet scale.
    </AlternatingDocBlock>
  );
}
