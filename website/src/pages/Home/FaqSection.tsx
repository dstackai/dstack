import { useState } from 'react';
import Button from '@cloudscape-design/components/button';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';

const faqItems = [
  {
    q: 'How does dstack differ from Slurm?',
    a: 'Slurm is a battle-tested system with decades of production use in HPC environments. dstack, by contrast, is built for modern ML/AI workloads with cloud-native provisioning and a container-first architecture. While both support distributed training and batch jobs, dstack also natively supports development and production-grade inference.',
  },
  {
    q: 'How does dstack compare to Kubernetes?',
    a: "Kubernetes is a general-purpose container orchestrator. dstack also orchestrates containers, but it provides a lightweight, streamlined interface that's purpose-built for ML. You declare dev environments, tasks, services, and fleets with simple configuration, and dstack provisions GPUs, manages clusters via fleets with fine-grained controls, and optimizes cost and utilization — all while keeping a simple CLI and UI.",
  },
  {
    q: 'Can I use dstack with Kubernetes?',
    a: 'Yes. You can connect existing Kubernetes clusters using the Kubernetes backend and run dev environments, tasks, and services on them. Choose the Kubernetes backend if your GPUs already run on Kubernetes and your team depends on its ecosystem and tooling — otherwise, VM-based backends (for cloud GPUs) or SSH fleets (for on-prem) are often a better fit.',
  },
  {
    q: 'When should I use dstack?',
    a: "dstack accelerates ML development with a simple, ML-native interface — spin up dev environments, run single-node or distributed tasks, and deploy services without infrastructure overhead. It radically reduces GPU costs through smart orchestration and fine-grained fleet controls, including efficient reuse, right-sizing, and support for spot, on-demand, and reserved capacity. It's 100% interoperable with your stack, working with any open-source frameworks and tools and your own Docker images and code, across GPU clouds, Kubernetes, and on-prem GPUs.",
  },
];

// FAQ block: a single-open accordion of questions beside contact actions.
export function FaqSection() {
  const [openQuestion, setOpenQuestion] = useState<string | null>(null);

  return (
    <section className="docs-section" id="faq">
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
                {item.a}
              </ExpandableSection>
            ))}
          </div>
        }
        title="FAQ"
        action={
          <Button variant="primary" href="https://discord.gg/dstack" target="_blank" iconAlign="right" iconName="external">
            Discord
          </Button>
        }
      >
        Have questions, or need help? Reach out to us on Discord or directly.
      </AlternatingDocBlock>
    </section>
  );
}
