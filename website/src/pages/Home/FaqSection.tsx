import { ReactNode, useState } from 'react';
import Button from '@cloudscape-design/components/button';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import Link from '@cloudscape-design/components/link';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { mainButtonStyle } from '../../cloudscape-theme';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';
import { highlightTerms } from '../../components/highlightTerms';
import { docsUrl } from '../../routes';

type FaqItem = {
  q: string;
  a: ReactNode;
};

const faqItems: FaqItem[] = [
  {
    q: 'How does dstack compare to Slurm?',
    a: [
      'Slurm is a battle-tested workload manager used in HPC and large-scale AI training. dstack is a unified orchestration layer built for containerized AI workloads and heterogeneous AI compute, with first-class primitives for compute management, training, inference, and observability.',
      'dstack can be used instead of Slurm to orchestrate AI workloads directly on cloud GPUs, pre-provisioned VMs, or bare-metal. It can also run on top of existing Slurm clusters through the Slurm backend.',
    ],
  },
  {
    q: 'How does dstack compare to Kubernetes?',
    a: [
      'Kubernetes is a general-purpose container orchestrator. dstack also orchestrates containers, but provides a lightweight, streamlined interface purpose-built for AI workloads, with first-class primitives for compute management, training, inference, and observability.',
      'dstack can be used instead of Kubernetes to orchestrate AI workloads directly on cloud GPUs, pre-provisioned VMs, or bare-metal. It can also run on top of existing Kubernetes clusters through the Kubernetes backend.',
    ],
  },
  {
    q: 'Can I use dstack with Kubernetes?',
    a: [
      <>
        {highlightTerms('Yes. Connect existing Kubernetes clusters through the ')}
        <Link href={docsUrl('concepts/backends/#kubernetes')}>{highlightTerms('Kubernetes backend')}</Link>
        {highlightTerms(', and dstack will schedule AI workloads on them alongside cloud GPUs, VMs, and bare-metal.')}
      </>,
      'Use the Kubernetes backend when your GPUs already run on Kubernetes or your team relies on its ecosystem and tooling. Otherwise, cloud backends are often simpler for cloud GPUs, and SSH fleets for pre-provisioned VMs or bare-metal.',
    ],
  },
  {
    q: 'Can I use dstack with Slurm?',
    a: [
      <>
        {highlightTerms('Yes. Connect existing Slurm clusters through the experimental ')}
        <Link href={docsUrl('concepts/backends/#slurm')}>{highlightTerms('Slurm backend')}</Link>
        {highlightTerms('. dstack connects to each cluster’s login node over SSH and submits runs as Slurm jobs.')}
      </>,
      'Slurm retains resource allocation and scheduling, while dstack provides the same interface for development, training, and inference used with other backends. The cluster must have Pyxis and enroot installed and configured.',
    ],
  },
  {
    q: 'When should I use dstack?',
    a: 'Use dstack as a unified orchestration layer for cluster management, training, and inference, built for heterogeneous AI compute. It is designed for cloud tenants, data-center operators, and AI token factories.',
  },
];

// FAQ block: a single-open accordion of questions beside contact actions.
export function FaqSection({ items = faqItems, showContact = true, imageFirst = false, action, children }: {
  items?: FaqItem[];
  showContact?: boolean;
  imageFirst?: boolean;
  action?: ReactNode;
  children?: ReactNode;
}) {
  const [openQuestion, setOpenQuestion] = useState<string | null>(null);

  return (
    <section className="docs-section" id="faq">
      <AlternatingDocBlock
        imageFirst={imageFirst}
        visual={
          <div className="faq-list">
            {items.map(item => (
              <ExpandableSection
                key={item.q}
                variant="stacked"
                headerText={item.q}
                expanded={openQuestion === item.q}
                onChange={({ detail }) => setOpenQuestion(detail.expanded ? item.q : null)}
              >
                {(Array.isArray(item.a) ? item.a : [item.a]).map((paragraph, index) => (
                  <p key={index}>{highlightTerms(paragraph)}</p>
                ))}
              </ExpandableSection>
            ))}
          </div>
        }
        title="FAQ"
        action={action ?? (
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="primary" href="https://discord.gg/u8SmfwPpMd" target="_blank" iconAlign="right" iconName="external" style={mainButtonStyle}>
              Discord
            </Button>
            {showContact && (
              <Button href="https://calendly.com/dstackai/discovery-call" target="_blank" iconAlign="right" iconName="external" style={mainButtonStyle}>
                Talk to us
              </Button>
            )}
          </SpaceBetween>
        )}
      >
        {children ?? <>Have questions, or need help? Reach out to us on Discord{showContact && ' or directly'}.</>}
      </AlternatingDocBlock>
    </section>
  );
}
