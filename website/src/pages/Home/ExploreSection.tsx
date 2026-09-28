import { ReactNode } from 'react';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';
import { ArchitectureDiagram } from '../../components/ArchitectureDiagram';
import { CapList } from '../../components/Capabilities';
import { ComputeSourcesTabs } from '../../components/ComputeSourcesTabs';
import { FleetGlyph, GatewayGlyph, PresetGlyph, ProjectGlyph, ServiceGlyph, TaskGlyph } from '../../components/ConceptIcons';
import { ContentTabs } from '../../components/ContentTabs';
import { ViewDocsButton } from '../../components/ViewDocsButton';
import { highlightTerms } from '../../components/highlightTerms';
import { DOCS_URL, docsUrl } from '../../routes';

// Core orchestration primitives shown in the "AI-native orchestration" block.
const keyConcepts = [
  { icon: <FleetGlyph />, title: 'Fleets', href: docsUrl('concepts/fleets'), sub: 'Cluster provisioning and monitoring' },
  { icon: <TaskGlyph />, title: 'Tasks', href: docsUrl('concepts/tasks'), sub: 'Training and other kind of jobs scheduling' },
  { icon: <ServiceGlyph />, title: 'Services', href: docsUrl('concepts/services'), sub: 'Cache-aware and PD-disaggregated inference' },
  { icon: <GatewayGlyph />, title: 'Gateways', href: docsUrl('concepts/gateways'), sub: 'HTTPS, auto-scaling, domains, and rate limits' },
  { icon: <PresetGlyph />, title: 'Presets', href: docsUrl('concepts/presets'), sub: 'Agent-based optimization toolkit' },
  { icon: <ProjectGlyph />, title: 'Projects', href: docsUrl('concepts/projects'), sub: 'Tenant isolation and usage metering' },
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
      through the Kubernetes backend or the experimental Slurm backend.
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
        <ContentTabs
          ariaLabel="AI-native orchestration"
          className="gs-box--compute-sources"
          tabs={[{
            id: 'concepts',
            label: 'Concepts',
            content: <CapList items={keyConcepts} />,
            footer: (
              <>
                <span className="gs-foot__note">
                  A unified interface for managing compute, training, and inference
                </span>
                <ViewDocsButton href={DOCS_URL} />
              </>
            ),
          }]}
        />
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
