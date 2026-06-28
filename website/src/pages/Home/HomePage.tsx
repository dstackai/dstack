import Button from '@cloudscape-design/components/button';
import { useLayoutContext } from '../../App';
import { heroButtonStyle } from '../../cloudscape-theme';
import { HeroSquircle } from '../../components/HeroSquircle';
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
              'dstack is an open-source orchestration layer for heterogeneous AI compute. ' +
              'It standardizes how workloads run across GPU clouds, Kubernetes, and on-prem clusters, ' +
              'across NVIDIA, AMD, Tenstorrent, and TPU accelerators.',
            )}
          </p>
          <div className="home-hero__actions">
            <Button
              variant="primary"
              href="#resources"
              onClick={event => {
                event.preventDefault();
                document.getElementById('resources')?.scrollIntoView({ behavior: 'smooth' });
              }}
              style={heroButtonStyle}
            >
              Get started
            </Button>
            <Button href={DOCS_URL} style={heroButtonStyle}>
              View docs
            </Button>
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
