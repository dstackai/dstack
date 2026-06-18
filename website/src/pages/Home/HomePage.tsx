import Button from '@cloudscape-design/components/button';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { images, ThemedImage } from '../../data/images';
import { DOCS_URL } from '../../routes';
import { ExploreSection } from './ExploreSection';
import { FaqSection } from './FaqSection';
import { GetStartedSection } from './GetStartedSection';
import { TrustedBySection } from './TrustedBySection';

const transparentButton = {
  root: { background: { default: 'transparent', hover: 'transparent', active: 'transparent' } },
};

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
            for AI infrastructure
          </h2>
          <p>
            dstack is a unified control plane for GPU provisioning and orchestration that works with any
            GPU cloud, Kubernetes, or on-prem clusters. It streamlines development, training, and inference,
            and is compatible with any hardware, open-source tools, and frameworks.
          </p>
          <div className="home-hero__actions">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="primary" onClick={scrollToResources}>
                Get started
              </Button>
              <Button href={DOCS_URL} style={transparentButton}>
                Documentation
              </Button>
            </SpaceBetween>
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
