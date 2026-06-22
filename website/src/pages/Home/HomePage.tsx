import Button from '@cloudscape-design/components/button';
import { heroButtonStyle } from '../../cloudscape-theme';
import { highlightTerms } from '../../components/highlightTerms';
import { images, ThemedImage } from '../../data/images';
import { DOCS_URL } from '../../routes';
import { ExploreSection } from './ExploreSection';
import { FaqSection } from './FaqSection';
import { GetStartedSection } from './GetStartedSection';
import { TrustedBySection } from './TrustedBySection';

// Hero artwork: both variants are rendered and CSS shows the one matching the theme.
function ThemedHeroImage({ image }: { image: ThemedImage }) {
  return (
    <>
      <img src={image.light} alt="" className="hero-slice hero-slice--light" />
      <img src={image.dark} alt="" className="hero-slice hero-slice--dark" />
    </>
  );
}

export function HomePage() {
  const scrollToResources = () =>
    document.getElementById('resources')?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  return (
    <main className="home-main">
      <section className="home-hero">
        <div className="home-hero__art" aria-hidden="true">
          <div className="site-frame home-hero__art-frame">
            <ThemedHeroImage image={images.hero} />
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
            <Button variant="primary" onClick={scrollToResources} style={heroButtonStyle}>
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

      {/* On phones the hero artwork is relocated down here, just above the footer
          (the top instance is hidden at the same breakpoint). */}
      <div className="site-frame home-hero-mobile-art" aria-hidden="true">
        <ThemedHeroImage image={images.hero} />
      </div>
    </main>
  );
}
