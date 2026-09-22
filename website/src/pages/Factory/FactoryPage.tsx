import { Fragment } from 'react';
import Button from '@cloudscape-design/components/button';
import { useLayoutContext } from '../../App';
import { heroButtonStyle, mainButtonStyle } from '../../cloudscape-theme';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';
import { HeroSquircle } from '../../components/HeroSquircle';
import { highlightTerms } from '../../components/highlightTerms';
import { FaqSection } from '../Home/FaqSection';
import { TrustedBySection } from '../Home/TrustedBySection';
import { CapacityTabs } from './CapacityTabs';
import { InferenceTabs } from './InferenceTabs';
import { OrchestrationTabs } from './OrchestrationTabs';
import { TenantTabs } from './TenantTabs';
import './FactoryPage.css';

const demoUrl = 'https://calendly.com/dstackai/discovery-call';

const features = [
  {
    title: 'A unified control plane',
    visual: <CapacityTabs />,
    paragraphs: [
      'dstack Factory connects your Kubernetes clusters, VMs, or bare-metal clusters to a unified ' +
        'control plane. Provision containers across your infrastructure and make better use of ' +
        'available capacity.',
      'Monitor resource utilization and the health of your accelerators and network. Identify ' +
        'failures and keep workloads running with automated recovery.',
    ],
  },
  {
    title: 'AI-native orchestration',
    visual: <OrchestrationTabs />,
    paragraphs: [
      'dstack Factory streamlines training and inference orchestration on heterogeneous compute. ' +
        'It operates at the container level, allowing you to use any open-source training or ' +
        'serving framework across your clusters.',
      'Inference services run on clusters with cache-aware routing and prefill/decode ' +
        'disaggregation. They scale with demand and support OpenAI-compatible HTTPS endpoints ' +
        'with custom domains and rate limits.',
    ],
  },
  {
    title: 'Serverless inference',
    visual: <InferenceTabs />,
    paragraphs: [
      'dstack Factory automates inference optimization on heterogeneous accelerators to increase ' +
        'throughput and lower cost per token. AI agents adapt the serving stack to your models ' +
        'and workloads, from framework tuning to custom kernel generation.',
      'Ready-to-use, optimized presets bring day-0 support for frontier open models on supported ' +
        'hardware. You can serve new models as soon as they are released, without a dedicated ' +
        'inference optimization team.',
    ],
  },
  {
    title: 'Multi-tenancy and billing',
    visual: <TenantTabs />,
    paragraphs: [
      'dstack Factory separates customers and teams into projects with their own users and ' +
        'resources. Selected capacity can be shared across projects with controlled access.',
      'Compute, storage, and token usage are metered per tenant. Automated billing manages ' +
        'customer charges, balances, and payments.',
    ],
  },
];

export function FactoryPage() {
  const { theme } = useLayoutContext();

  return (
    <main className="home-main">
      <section className="home-hero">
        <div className="home-hero__art" aria-hidden="true">
          <div className="site-frame home-hero__art-frame">
            <HeroSquircle
              theme={theme}
              topLabel="AI token"
              paletteId="13"
              ariaLabel="dstack Factory"
            />
          </div>
        </div>
        <div className="site-frame home-hero__content">
          <h1 className="factory-hero-title">
            A heterogeneous stack for AI token factories
          </h1>
          <p>
            {highlightTerms(
              'dstack Factory is a heterogeneous orchestration stack for AI token factories. ' +
              'It streamlines capacity management, training, and inference deployment and optimization. ' +
              'It includes day-0 support for frontier open models, multi-tenancy, and billing automation.',
            )}
          </p>
          <div className="home-hero__actions home-hero__actions--single">
            <Button
              variant="primary"
              href={demoUrl}
              target="_blank"
              iconName="external"
              iconAlign="right"
              style={heroButtonStyle}
            >
              Book a demo
            </Button>
          </div>
        </div>
      </section>

      <div className="site-frame home-stack home-no-rail">
        <div className="docs-body docs-body--no-rail">
          <article className="docs-article">
            <section className="docs-section explore-section" id="resources">
              {features.map((feature, index) => (
                <AlternatingDocBlock
                  key={feature.title}
                  visual={feature.visual}
                  title={feature.title}
                  imageFirst={index % 2 === 0}
                >
                  {feature.paragraphs.map((paragraph, paragraphIndex) => (
                    <Fragment key={paragraph}>
                      {paragraphIndex > 0 && <><br /><br /></>}
                      {highlightTerms(paragraph)}
                    </Fragment>
                  ))}
                </AlternatingDocBlock>
              ))}
            </section>

            <FaqSection
              imageFirst
              action={
                <Button
                  variant="primary"
                  href={demoUrl}
                  target="_blank"
                  iconName="external"
                  iconAlign="right"
                  style={mainButtonStyle}
                >
                  Talk to us
                </Button>
              }
              items={[
                {
                  q: 'How is dstack Factory different from dstack?',
                  a: [
                    'dstack is the open-source orchestration layer for heterogeneous AI compute. ' +
                      'It provides compute management, training, inference, and observability. ' +
                      'dstack Factory uses the same CLI and supports the same YAML configurations.',
                    'dstack Factory extends dstack with advanced multi-tenancy, usage metering, ' +
                      'and billing automation. It provides day-0 support for frontier open models ' +
                      'through ready-to-use, optimized inference presets.',
                  ],
                },
              ]}
            >
              Talk to us about your infrastructure, models, and requirements for running an AI
              token factory.
            </FaqSection>

            <TrustedBySection />
          </article>
        </div>
      </div>
    </main>
  );
}
