import Button from '@cloudscape-design/components/button';
import { useLayoutContext } from '../../App';
import { heroButtonStyle } from '../../cloudscape-theme';
import { HeroSquircle } from '../../components/HeroSquircle';
import { ViewDocsButton } from '../../components/ViewDocsButton';
import { highlightTerms } from '../../components/highlightTerms';
import { DOCS_URL } from '../../routes';
import { ExploreSection } from './ExploreSection';
import { FaqSection } from './FaqSection';
import { GetStartedSection } from './GetStartedSection';
import { TrustedBySection } from './TrustedBySection';

export function HomePage() {
  const { theme } = useLayoutContext();
  return (
    <main className="home-main">
      <section className="home-hero">
        <div className="home-hero__art" aria-hidden="true">
          <div className="site-frame home-hero__art-frame">
            <HeroSquircle theme={theme} />
          </div>
        </div>
        <div className="site-frame home-hero__content">
          <h2>
            The orchestration stack
            <br />
            for heterogeneous AI compute
          </h2>
          <p>
            {highlightTerms(
              'dstack is an open-source orchestration layer for AI workloads on heterogeneous accelerators. ' +
              'It standardizes how you manage compute and run training and inference on GPU clouds, ' +
              'Kubernetes, VMs, or bare-metal clusters.',
            )}
          </p>
          <div className="home-hero__actions cta-pair">
            <Button
              variant="primary"
              fullWidth
              href="#resources"
              onClick={event => {
                event.preventDefault();
                document.getElementById('resources')?.scrollIntoView({ behavior: 'smooth' });
              }}
              style={heroButtonStyle}
            >
              Get started
            </Button>
            <ViewDocsButton href={DOCS_URL} style={heroButtonStyle} fullWidth />
          </div>
        </div>
      </section>

      <div className="site-frame home-stack home-no-rail">
        <div className="docs-body docs-body--no-rail">
          <article className="docs-article">
            <ExploreSection />
            <FaqSection />
            <TrustedBySection />
            <GetStartedSection />
          </article>
        </div>
      </div>
    </main>
  );
}
