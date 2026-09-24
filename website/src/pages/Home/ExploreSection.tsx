import { ReactNode } from 'react';
import Link from '@cloudscape-design/components/link';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';
import { ArchitectureDiagram } from '../../components/ArchitectureDiagram';
import { ComputeSourcesTabs } from '../../components/ComputeSourcesTabs';
import { highlightTerms } from '../../components/highlightTerms';
import { docsUrl } from '../../routes';

// Core orchestration primitives shown in the "AI-native orchestration" block.
const keyConcepts = [
  { name: 'Fleets', href: docsUrl('concepts/fleets'), description: 'Cluster provisioning and monitoring' },
  { name: 'Tasks', href: docsUrl('concepts/tasks'), description: 'Training and other kind of jobs scheduling' },
  { name: 'Services', href: docsUrl('concepts/services'), description: 'Cache-aware and PD-disaggregated inference' },
  { name: 'Gateways', href: docsUrl('concepts/gateways'), description: 'HTTPS, auto-scaling, domains, and rate limits' },
  { name: 'Presets', href: docsUrl('concepts/presets'), description: 'Agent-based optimization toolkit' },
  { name: 'Projects', href: docsUrl('concepts/projects'), description: 'Tenant isolation and usage metering' },
];

// The main marketing content: a sequence of alternating documentation blocks.
export function ExploreSection() {
  return (
    <section className="docs-section explore-section" id="explore">
      <AlternatingDocBlock visual={<ArchitectureDiagram />} title="Vendor-agnostic, open-source" imageFirst>
        dstack gives cloud tenants and data-center operators a unified control plane for managing compute and orchestrating AI workloads.
        <br />
        <br />
        It improves operational efficiency and removes vendor lock-in. Use your existing infrastructure without building and maintaining your own AI compute stack.
      </AlternatingDocBlock>

      <KeyConceptsBlock />

      <BringComputeBlock />

    </section>
  );
}

// Tabbed on-prem capabilities and GPU clouds for bring-your-own compute.
function BringComputeBlock() {
  return (
    <AlternatingDocBlock
      visual={<ComputeSourcesTabs />}
      title="Bring your own compute"
      imageFirst
    >
      Have bare-metal servers or VMs with SSH access? Point dstack to those hosts and provide SSH
      credentials to create an SSH fleet. Have an existing Kubernetes or Slurm cluster? Connect it
      through the Kubernetes backend or the <Link href={docsUrl('concepts/backends/#slurm')}>{highlightTerms('experimental Slurm backend')}</Link>.
      dstack provides a unified workload interface while Kubernetes or Slurm handles scheduling
      within the cluster.
      <br />
      <br />
      dstack natively integrates with the major GPU clouds and automates provisioning of clusters.
      Authorize dstack by configuring backends with your credentials, and dstack will provision fleets
      and schedule workloads in your own cloud account.
    </AlternatingDocBlock>
  );
}

export function KeyConceptsBlock({ children, imageFirst = false }: {
  children?: ReactNode;
  imageFirst?: boolean;
}) {
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
      imageFirst={imageFirst}
    >
      {children ?? <>
        Managing AI infrastructure requires first-class primitives for compute management, training, inference, and observability that support heterogeneous AI compute.
        <br />
        <br />
        {highlightTerms('dstack provides a streamlined interface to efficiently utilize cloud compute, run data-center operations, or run your own AI token factory at planet scale.')}
      </>}
    </AlternatingDocBlock>
  );
}
