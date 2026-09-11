import { useState } from 'react';
import Button from '@cloudscape-design/components/button';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { mainButtonStyle } from '../../cloudscape-theme';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';
import { highlightTerms } from '../../components/highlightTerms';

const faqItems = [
  {
    q: 'How does dstack differ from Slurm?',
    a: 'Slurm is a battle-tested workload manager with decades of production use in HPC environments. dstack is a unified orchestration layer built for containerized AI workloads and heterogeneous AI compute. While both support batch jobs and distributed training, dstack also provides first-class primitives for compute management, inference, and observability, including native cloud provisioning.',
  },
  {
    q: 'How does dstack compare to Kubernetes?',
    a: 'Kubernetes is a general-purpose container orchestrator. dstack also orchestrates containers, but provides a lightweight, streamlined interface purpose-built for AI workloads, with first-class primitives for compute management, training, inference, and observability. It can use Kubernetes as a compute backend or work directly with cloud GPUs, pre-provisioned VMs, or bare-metal, helping cloud tenants and data-center operators improve utilization without building and maintaining their own AI orchestration stack.',
  },
  {
    q: 'Can I use dstack with Kubernetes?',
    a: 'Yes. Connect existing Kubernetes clusters through the Kubernetes backend, and dstack will schedule AI workloads on them alongside cloud GPUs, VMs, and bare-metal. Use the Kubernetes backend when your GPUs already run on Kubernetes or your team relies on its ecosystem and tooling. Otherwise, cloud backends are often simpler for cloud GPUs, and SSH fleets for pre-provisioned VMs or bare-metal.',
  },
  {
    q: 'When should I use dstack?',
    a: 'Use dstack as a unified orchestration layer for cluster management, training, and inference, built for heterogeneous AI compute. It is designed for cloud tenants, data-center operators, and teams running their own AI token factory at planet scale.',
  },
];

// FAQ block: a single-open accordion of questions beside contact actions.
export function FaqSection() {
  const [openQuestion, setOpenQuestion] = useState<string | null>(null);

  return (
    <section className="docs-section" id="faq">
      {/* No imageFirst: the merged compute block above is visual-left, so the FAQ alternates back
          to visual-right. */}
      <AlternatingDocBlock
        visual={
          <div className="faq-list">
            {faqItems.map(item => (
              <ExpandableSection
                key={item.q}
                variant="stacked"
                headerText={item.q}
                expanded={openQuestion === item.q}
                onChange={({ detail }) => setOpenQuestion(detail.expanded ? item.q : null)}
              >
                {highlightTerms(item.a)}
              </ExpandableSection>
            ))}
          </div>
        }
        title="FAQ"
        action={
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="primary" href="https://discord.gg/u8SmfwPpMd" target="_blank" iconAlign="right" iconName="external" style={mainButtonStyle}>
              Discord
            </Button>
            <Button href="https://calendly.com/dstackai/discovery-call" target="_blank" iconAlign="right" iconName="external" style={mainButtonStyle}>
              Contact us
            </Button>
          </SpaceBetween>
        }
      >
        Have questions, or need help? Reach out to us on Discord or directly.
      </AlternatingDocBlock>
    </section>
  );
}
