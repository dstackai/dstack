import CodeView from '@cloudscape-design/code-view/code-view';
import yamlHighlight from '@cloudscape-design/code-view/highlight/yaml';
import Button from '@cloudscape-design/components/button';
import Icon from '@cloudscape-design/components/icon';
import Tabs from '@cloudscape-design/components/tabs';
import { mainButtonStyle } from '../../cloudscape-theme';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';
import { ArchitectureDiagram } from '../../components/ArchitectureDiagram';
import { DashedBorder } from '../../components/DashedBorder';
import { highlightTerms } from '../../components/highlightTerms';
import { gpuOffers } from '../../data/gpus';
import { docsUrl } from '../../routes';
import {
  backendConfigs,
  clusterConfigs,
  maxBackendYamlLines,
  maxClusterYamlLines,
  padYamlToLines,
} from '../../data/snippets';

// Core orchestration primitives shown in the "AI-native orchestration" block.
const keyConcepts = [
  { name: 'Fleets', label: 'Cloud & on-prem', href: docsUrl('concepts/fleets'), description: 'Provision and manage clusters across clouds, Kubernetes, and on-prem.' },
  { name: 'Dev environments', label: 'Development', href: docsUrl('concepts/dev-environments'), description: 'Launch dev environments to be accessed by agents or from your IDE.' },
  { name: 'Tasks', label: 'Training and batch', href: docsUrl('concepts/tasks'), description: 'Run training and batch jobs across a single node or clusters.' },
  { name: 'Services', label: 'Model inference', href: docsUrl('concepts/services'), description: 'Deploy model inference as secure and scalable endpoints.' },
];

// Read-only YAML snippet. Line wrapping is left off so one line maps to one row,
// which keeps padded snippets equal height across tabs (see padYamlToLines).
function YamlCode({ content }: { content: string }) {
  return (
    <div className="code-snippet">
      <CodeView ariaLabel="YAML configuration" content={content} highlight={yamlHighlight} />
    </div>
  );
}

// GPU price list — a plain monospace name/price list in a bordered card, matching the dstack Sky
// "GPU marketplace" pane in the Get started section (same .gs-mkt__row treatment, single source).
function GpuMarketplaceTable() {
  return (
    <div className="gpu-mkt">
      <ul className="gpu-mkt__list">
        {gpuOffers.map(offer => (
          <li className="gs-mkt__row" key={`${offer.name} ${offer.memory}`}>
            <span className="gs-mkt__g"><span className="gs-mkt__name">{offer.name}</span>{' '}{offer.memory}</span>
            <span className="gs-mkt__p">{offer.price}/hr</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// The main marketing content: a sequence of alternating documentation blocks.
export function ExploreSection() {
  return (
    <section className="docs-section explore-section" id="explore">
      <AlternatingDocBlock visual={<ArchitectureDiagram />} title="Vendor-agnostic, open-source" imageFirst>
        dstack unifies fleets, dev environments, tasks, services, volumes, and gateways in one control plane for AI workloads.
        <br />
        <br />
        It’s built for containerized AI workloads with a simple CLI, UI, and API. No Kubernetes or Slurm hassle required.
      </AlternatingDocBlock>

      <KeyConceptsBlock />

      <AlternatingDocBlock
        visual={
          <Tabs
            variant="container"
            ariaLabel="Cloud backend"
            tabs={backendConfigs.map(backend => ({
              id: backend.id,
              label: backend.label,
              content: <YamlCode content={padYamlToLines(backend.yaml, maxBackendYamlLines)} />,
            }))}
          />
        }
        title="Bring your own clouds"
        imageFirst
      >
        dstack natively integrates with the major GPU clouds and automates provisioning of clusters.
        <br />
        <br />
        Authorize dstack by providing credentials, and dstack will provision compute and schedule workloads
        in your own cloud account.
      </AlternatingDocBlock>

      <AlternatingDocBlock
        visual={
          <Tabs
            variant="container"
            ariaLabel="Cluster type"
            tabs={clusterConfigs.map(cluster => ({
              id: cluster.id,
              label: cluster.label,
              content: <YamlCode content={padYamlToLines(cluster.yaml, maxClusterYamlLines)} />,
            }))}
          />
        }
        title="Bring on-prem clusters"
      >
        Have an existing Kubernetes cluster? Point dstack to the kubeconfig, and dstack
        will schedule workloads on it as it was a cloud cluster.
        <br />
        <br />
        Have bare-metal servers or VMs with SSH access? Point dstack to those hosts and provide SSH credentials, and dstack will
        schedule workloads on them alongside Kubernetes and cloud clusters.
      </AlternatingDocBlock>

      <GpuMarketplaceBlock />
    </section>
  );
}

function KeyConceptsBlock() {
  return (
    <AlternatingDocBlock
      visual={
        <div className="concept-grid">
          {keyConcepts.map(concept => (
            // Whole card is the link so it reads as clickable, with an ActionCard-style
            // arrow. Kept as a real <a> (open-in-new-tab / SEO) rather than Cloudscape's
            // onClick-only ActionCard component.
            <a className="media-card concept-card" href={concept.href} key={concept.name}>
              <DashedBorder />
              <span className="concept-card__label">{concept.label}</span>
              <h3>
                {concept.name}
                <span className="concept-card__arrow" aria-hidden="true"><Icon name="angle-right" /></span>
              </h3>
              <p>{highlightTerms(concept.description)}</p>
            </a>
          ))}
        </div>
      }
      title="AI-native orchestration"
    >
      Managing AI infrastructure requires first-class primitives for accelerator provisioning, workload scheduling, and observability.
      <br />
      <br />
      dstack offers a streamlined interface for development, training, and inference built for heterogeneous AI compute.
    </AlternatingDocBlock>
  );
}

function GpuMarketplaceBlock() {
  return (
    <AlternatingDocBlock
      visual={<GpuMarketplaceTable />}
      title="Access marketplace GPUs"
      imageFirst
      action={<Button href="https://sky.dstack.ai" target="_blank" iconName="external" iconAlign="right" style={mainButtonStyle}>Try dstack Sky</Button>}
    >
      Don't have your own cloud accounts or on-prem clusters? No problem. You can access compute
      through dstack Sky, our hosted GPU marketplace.
      <br />
      <br />
      It's possible to use dstack Sky alongside with your own cloud accounts or on-prem clusters.
    </AlternatingDocBlock>
  );
}
