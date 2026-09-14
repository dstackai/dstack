import { KeyboardEvent, useRef, useState } from 'react';
import Button from '@cloudscape-design/components/button';
import { useLayoutContext } from '../../App';
import { heroButtonStyle, mainButtonStyle } from '../../cloudscape-theme';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';
import { highlightTerms } from '../../components/highlightTerms';
import { KeyConceptsBlock } from '../Home/ExploreSection';
import { FaqSection } from '../Home/FaqSection';
import { CapList, ChipGlyph, CloudGlyph, KubernetesGlyph, ServerGlyph } from '../Home/GetStartedSection';
import { TrustedBySection } from '../Home/TrustedBySection';
import { HeroSquircle } from './HeroSquircle';
import { gpuPrices } from './pricing';

const computeTabs = ['On-demand', 'Reserved clusters', 'BYOC'];

export function SkyPage() {
  const { theme } = useLayoutContext();
  const [computeTab, setComputeTab] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const nextIndex = {
      ArrowRight: (index + 1) % computeTabs.length,
      ArrowLeft: (index + computeTabs.length - 1) % computeTabs.length,
      Home: 0,
      End: computeTabs.length - 1,
    }[event.key];
    if (nextIndex === undefined) return;
    event.preventDefault();
    setComputeTab(nextIndex);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <main className="home-main home-main--sky">
      <section className="home-hero">
        <div className="home-hero__art" aria-hidden="true">
          <div className="site-frame home-hero__art-frame">
            <HeroSquircle theme={theme} />
          </div>
        </div>
        <div className="site-frame home-hero__content">
          <h1>The AI cloud with AI-native orchestration</h1>
          <p>
            {highlightTerms(
              'dstack Sky is a heterogeneous AI cloud with NVIDIA Blackwell, Hopper, and AMD Instinct GPUs. ' +
              'Built on dstack, it combines compute management, training, inference, ' +
              'and observability in one interface.',
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
                visual={
                  <div className={`gs-box gs-box--compute${computeTab === 0 ? ' gs-box--offers' : ''}`}>
                    <div className="gs-tabs" role="tablist" aria-label="Compute options">
                      {computeTabs.map((label, index) => (
                        <button
                          key={label}
                          ref={element => { tabRefs.current[index] = element; }}
                          id={`sky-compute-tab-${index}`}
                          type="button"
                          role="tab"
                          aria-selected={computeTab === index}
                          aria-controls={`sky-compute-panel-${index}`}
                          tabIndex={computeTab === index ? 0 : -1}
                          className={`gs-tab${computeTab === index ? ' gs-tab--on' : ''}`}
                          onClick={() => setComputeTab(index)}
                          onKeyDown={event => onTabKeyDown(event, index)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <div
                      key={computeTab}
                      className="gs-skybody"
                      id={`sky-compute-panel-${computeTab}`}
                      role="tabpanel"
                      aria-labelledby={`sky-compute-tab-${computeTab}`}
                      tabIndex={0}
                    >
                      {computeTab === 0 && (
                        <table className="sky-gpu-prices" aria-label="GPU prices in USD per GPU-hour">
                          <thead>
                            <tr>
                              <th scope="col">GPU</th>
                              <th scope="col">On-demand</th>
                              <th scope="col">Spot</th>
                            </tr>
                          </thead>
                          <tbody>
                            {gpuPrices.map(gpu => (
                              <tr key={`${gpu.name} ${gpu.memory}`}>
                                <th scope="row">
                                  <span className="gs-mkt__left">
                                    <span className="gs-li__ic"><ChipGlyph /></span>
                                    <span className="gs-mkt__g"><span className="gs-mkt__name">{gpu.name}</span>{' '}{gpu.memory}</span>
                                  </span>
                                </th>
                                <td>{gpu.onDemand}</td>
                                <td>{gpu.spot ?? '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                      {computeTab === 1 && (
                        <CapList items={[
                          { icon: <ServerGlyph />, title: 'GPU clusters', sub: 'Reserve for a fixed period at a price agreed in advance' },
                        ]} />
                      )}
                      {computeTab === 2 && (
                        <CapList items={[
                          { icon: <CloudGlyph />, title: 'GPU clouds', sub: 'AWS, GCP, Azure, Nebius, Runpod, and more' },
                          { icon: <ServerGlyph />, title: 'SSH fleets', sub: 'Pre-provisioned VMs or bare-metal' },
                          { icon: <KubernetesGlyph />, title: 'Kubernetes', sub: 'Existing Kubernetes clusters' },
                        ]} />
                      )}
                    </div>
                    <div className="gs-boxfoot">
                      {computeTab !== 1 && (
                        <span className="gs-foot__note">
                          {computeTab === 0 ? 'Prices in USD per GPU-hour' : 'Bring your own compute'}
                        </span>
                      )}
                      {computeTab === 1 && (
                        <Button
                          href="https://calendly.com/dstackai/discovery-call"
                          target="_blank"
                          iconName="external"
                          iconAlign="right"
                          style={mainButtonStyle}
                        >
                          Contact us
                        </Button>
                      )}
                    </div>
                  </div>
                }
                title="On-demand GPUs for AI workloads"
                imageFirst
              >
                Access affordable on-demand and spot GPUs with pay-as-you-go pricing.
                <br />
                <br />
                You can also bring compute from your own cloud accounts or on-prem infrastructure
                and use it alongside Sky GPUs.
              </AlternatingDocBlock>

              <KeyConceptsBlock>
                dstack Sky provides first-class primitives for compute management, training,
                inference, and observability across heterogeneous AI compute. Use one interface
                to efficiently utilize cloud GPUs, manage your own clusters, or run your own
                AI token factory at scale.
                <br />
                <br />
                Sky is built on dstack and uses the same CLI and YAML configurations as a
                self-hosted dstack server.
              </KeyConceptsBlock>
            </section>

            <FaqSection imageFirst items={[
              {
                q: 'How is dstack Sky different from dstack?',
                a: 'dstack is an open-source orchestration stack that you host yourself. ' +
                  'dstack Sky is hosted by us and provides GPU compute on demand. ' +
                  'You can also bring compute from your own cloud accounts or on-prem infrastructure. ' +
                  'Both use the same CLI and YAML configurations.',
              },
            ]} />

            <TrustedBySection />
          </article>
        </div>
      </div>
    </main>
  );
}
