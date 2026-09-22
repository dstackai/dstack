import Button from '@cloudscape-design/components/button';
import { useLayoutContext } from '../../App';
import { heroButtonStyle } from '../../cloudscape-theme';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';
import { ComputeSourcesTabs } from '../../components/ComputeSourcesTabs';
import { highlightTerms } from '../../components/highlightTerms';
import { KeyConceptsBlock } from '../Home/ExploreSection';
import { FaqSection } from '../Home/FaqSection';
import { TrustedBySection } from '../Home/TrustedBySection';
import { HeroSquircle } from './HeroSquircle';
import { MarketplaceTabs } from './MarketplaceTabs';

export function SkyPage() {
  const { theme } = useLayoutContext();

  return (
    <main className="home-main home-main--sky">
      <section className="home-hero">
        <div className="home-hero__art" aria-hidden="true">
          <div className="site-frame home-hero__art-frame">
            <HeroSquircle theme={theme} />
          </div>
        </div>
        <div className="site-frame home-hero__content">
          <h1>One account across GPU clouds</h1>
          <p>
            {highlightTerms(
              'dstack Sky combines GPU capacity from multiple cloud partners with competitive pricing, ' +
              'unified billing, and AI-native orchestration. We host and manage the dstack server for you, ' +
              'whether you use on-demand and spot GPUs from the marketplace or bring your own cloud and on-prem compute.',
            )}
          </p>
          <div className="home-hero__actions">
            <Button
              variant="primary"
              href="https://sky.dstack.ai/"
              target="_blank"
              iconName="external"
              iconAlign="right"
              style={heroButtonStyle}
            >
              Sign up
            </Button>
          </div>
        </div>
      </section>

      <div className="site-frame home-stack home-no-rail">
        <div className="docs-body docs-body--no-rail">
          <article className="docs-article">
            <section className="docs-section explore-section" id="compute">
              <AlternatingDocBlock
                visual={<MarketplaceTabs />}
                title="Better prices, unified billing"
                imageFirst
              >
                The dstack Sky marketplace offers on-demand and spot GPUs from a wide set of partners.
                You get competitive pricing and capacity across regions, without depending on a
                single cloud.
                <br />
                <br />
                One dstack Sky account gives you access to all marketplace partners. Billing is unified,
                with no separate cloud accounts to manage.
              </AlternatingDocBlock>

              <AlternatingDocBlock
                visual={<ComputeSourcesTabs cloudsFirst />}
                title="Bring your own compute"
              >
                dstack Sky provisions and manages compute in your own GPU cloud accounts using your
                credentials. Compute is billed directly to those accounts.
                <br />
                <br />
                You can also bring on-prem compute, including Kubernetes clusters, pre-provisioned
                VMs, and bare-metal clusters. We host and maintain the dstack server for you.
              </AlternatingDocBlock>

              <KeyConceptsBlock imageFirst>
                dstack Sky provides first-class primitives for compute management, training,
                inference, and observability across heterogeneous AI compute.
                <br />
                <br />
                dstack Sky includes all the features of open-source dstack and uses the same CLI and
                YAML configurations. It adds a built-in gateway with an HTTPS domain, advanced
                observability, and usage metering.
              </KeyConceptsBlock>
            </section>

            <FaqSection showContact={false} items={[
              {
                q: 'How is dstack Sky different from dstack?',
                a: [
                  'With dstack Sky, we host and maintain the server for you. ' +
                    'With open-source dstack, you host the server yourself.',
                  'dstack Sky includes all open-source features and adds a built-in gateway with an HTTPS domain, advanced observability, and usage metering.',
                  'dstack Sky also provides a GPU marketplace with unified billing. ' +
                    'Both support your own cloud accounts and on-prem compute. ' +
                    'The CLI and YAML configurations are the same.',
                ],
              },
            ]} />

            <TrustedBySection />
          </article>
        </div>
      </div>
    </main>
  );
}
