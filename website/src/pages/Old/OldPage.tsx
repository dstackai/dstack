import { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import AnchorNavigation from '@cloudscape-design/components/anchor-navigation';
import AppLayoutToolbar from '@cloudscape-design/components/app-layout-toolbar';
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group';
import Button from '@cloudscape-design/components/button';
import Link from '@cloudscape-design/components/link';
import SideNavigation, { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { images } from '../../data/images';
import { DOCS_URL, ROUTES } from '../../routes';
import { useLayoutContext } from '../../App';

// Side navigation for the Old page (kept for comparison; links are illustrative anchors).
const docsNavigationItems: SideNavigationProps.Item[] = [
  {
    type: 'section-group',
    title: 'For designers',
    items: [
      { type: 'link', text: 'Start designing', href: '#/designers/start-designing' },
      { type: 'link', text: 'Design resources', href: '#/designers/design-resources' },
    ],
  },
  { type: 'divider' },
  {
    type: 'section-group',
    title: 'For developers',
    items: [
      { type: 'link', text: 'Start developing', href: '#/developers/start-developing' },
      { type: 'link', text: 'Using Cloudscape components', href: '#/developers/using-components' },
      { type: 'link', text: 'Global styles', href: '#/developers/global-styles' },
      { type: 'link', text: 'Built-in internationalization', href: '#/developers/i18n' },
      { type: 'link', text: 'AI Tools Support', href: '#/developers/ai-tools' },
    ],
  },
];

// The previous home page content, kept for comparison while we iterate. The side
// navigation drawer state is owned by the App layout (shared with the top nav trigger).
export function OldPage() {
  const navigate = useNavigate();
  const { oldNavigationOpen, setOldNavigationOpen } = useLayoutContext();

  return (
    <AppLayoutToolbar
      className={`docs-shell docs-shell--old-page ${oldNavigationOpen ? 'docs-shell--navigation-open' : 'docs-shell--navigation-collapsed'}`}
      headerSelector=".site-nav"
      footerSelector=".site-footer"
      navigationOpen={oldNavigationOpen}
      onNavigationChange={event => setOldNavigationOpen(event.detail.open)}
      navigationTriggerHide
      navigationWidth={280}
      toolsHide
      maxContentWidth={Number.MAX_VALUE}
      ariaLabels={{
        navigation: 'Side navigation',
        navigationClose: 'Close side navigation',
        navigationToggle: 'Open side navigation',
      }}
      navigation={
        <SideNavigation
          activeHref="#/designers/start-designing"
          header={{ text: 'Get started', href: '#/get-started' }}
          items={docsNavigationItems}
          onFollow={event => {
            event.preventDefault();
            if (event.detail.href === '#/') navigate(ROUTES.HOME);
          }}
        />
      }
      content={
        <div className="docs-main">
          <BreadcrumbGroup
            items={[
              { text: 'Cloudscape Design System', href: '#/' },
              { text: 'Old page', href: '#/old' },
            ]}
            onFollow={event => {
              event.preventDefault();
              if (event.detail.href === '#/') navigate(ROUTES.HOME);
            }}
          />
          <header className="docs-title">
            <h1>Old page</h1>
            <p>The previous home page content kept for comparison while we iterate.</p>
          </header>
          <div className="docs-body">
            <article className="docs-article">
              <OldHomeSections />
            </article>
            <DocsRightRail
              onThisPageId="old-on-this-page"
              anchors={[
                { text: 'Meet Cloudscape', href: '#meet', level: 1 },
                { text: 'Get familiar with the system', href: '#familiar', level: 1 },
                { text: 'Cloudscape on GitHub', href: '#github', level: 1 },
                { text: 'Overview', href: '#overview', level: 1 },
                { text: 'Start building', href: '#start-building', level: 1 },
              ]}
            />
          </div>
        </div>
      }
    />
  );
}

// "On this page" right rail with scroll-spy anchors and feedback blocks.
function DocsRightRail({
  onThisPageId,
  anchors,
}: {
  onThisPageId: string;
  anchors: Array<{ text: string; href: string; level: 1 }>;
}) {
  return (
    <aside className="docs-right">
      <h2 id={onThisPageId}>On this page</h2>
      <AnchorNavigation ariaLabelledby={onThisPageId} scrollSpyOffset={110} anchors={anchors} />
      <div className="right-rail-block">
        <h2>About this page</h2>
        <p>Published: May 31, 2022</p>
      </div>
      <div className="right-rail-block">
        <h2>Did this page help you?</h2>
        <p>Your feedback helps us improve our documentation.</p>
        <SpaceBetween size="xs">
          <SpaceBetween direction="horizontal" size="xs">
            <Button iconName="thumbs-up">Yes</Button>
            <Button iconName="thumbs-down">No</Button>
          </SpaceBetween>
          <Link href="#feedback">Provide additional feedback</Link>
        </SpaceBetween>
      </div>
    </aside>
  );
}

function OldHomeSections() {
  return (
    <>
      <ImageTextRow id="meet" image={images.meet} title="Meet Cloudscape" imageFirst>
        <p>
          Cloudscape is an open source design system to create web applications. It was built for
          and is used by Amazon Web Services (AWS) products and services.
        </p>
        <p>
          We created it in 2016 to improve the user experience across web applications owned by AWS
          services, and also to help teams implement those applications faster. Since then, we have
          continued enhancing the system based on customer feedback and research. Learn more{' '}
          <Link href="#about">about the system</Link>.
        </p>
      </ImageTextRow>
      <ImageTextRow id="familiar" image={images.familiar} title="Get familiar with the system">
        <p>
          Each <Link href="#components">component</Link> has a playground where designers and
          developers can see how the component behaves, along with sample code. To save you time and
          effort when building, we offer extensive guidance on accessibility options and design
          solutions. Head over to our <Link href="#demos">demos</Link> for examples of Cloudscape in action.
        </p>
      </ImageTextRow>
      <ImageTextRow id="github" image={images.github} title="Cloudscape on GitHub" imageFirst>
        <p>
          We publish our source code on GitHub under the <Link href="#license">Apache 2.0 License</Link>{' '}
          in the <Link href="#org">cloudscape-design</Link> organization. In our{' '}
          <Link href="#repo">main components repository</Link> you can find information about our support
          and contribution model, versioning strategy, and change logs. You can also{' '}
          <Link href="#issues">open issues</Link> and <Link href="#discussion">ask a question</Link>.
        </p>
      </ImageTextRow>
      <Overview />
      <CoreFeatureCards />
      <StartBuilding />
    </>
  );
}

function ImageTextRow({
  id,
  image,
  title,
  children,
  imageFirst = false,
}: {
  id?: string;
  image: string;
  title: string;
  children: ReactNode;
  imageFirst?: boolean;
}) {
  return (
    <section id={id} className={`image-text-row ${imageFirst ? 'image-first' : ''}`}>
      <div className="landing-copy">
        <h2>{title}</h2>
        <div>{children}</div>
      </div>
      <img src={image} alt="" className="landing-image" />
    </section>
  );
}

function Overview() {
  return (
    <section className="overview-section" id="overview">
      <h2>Overview</h2>
      <div className="stats-grid">
        <Stat value="94" text="Code components tested, responsive, and accessible" />
        <Stat value="62" text="Pattern guidelines that help users achieve their goals" />
        <Stat value="33" text="Demo pages showcasing the system in action" />
      </div>
    </section>
  );
}

function Stat({ value, text }: { value: string; text: string }) {
  return (
    <article className="stat-card">
      <span>{value}</span>
      <p>{text}</p>
    </article>
  );
}

function CoreFeatureCards() {
  const cards: Array<[string, string]> = [
    ['Light/Dark mode', images.mode],
    ['Theming', images.theming],
    ['Accessibility', images.accessibility],
    ['Responsiveness', images.responsive],
  ];
  return (
    <section className="core-features">
      <h3>Core features</h3>
      <p>
        Cloudscape supports various visual modes, accessibility, responsive design, and broad browser
        coverage. Services built with Cloudscape are designed for all customers, regardless of browser,
        screen size, or ability.
      </p>
      <div className="feature-card-grid">
        {cards.map(([title, image]) => (
          <article className="media-card" key={title}>
            <img src={image} alt="" />
            <h3>
              <Link href={`#${title.toLowerCase().replace(/\//g, '-')}`}>{title}</Link>
            </h3>
          </article>
        ))}
      </div>
    </section>
  );
}

function StartBuilding() {
  return (
    <section className="start-building" id="start-building">
      <h2>Start building</h2>
      <div className="start-grid">
        <article>
          <h3>For designers</h3>
          <p>
            <Link href={DOCS_URL}>Get started</Link>{' '}
            with designing accessible and intuitive interfaces. Use our{' '}
            <Link href="#visual">visual foundation</Link>, <Link href="#patterns">UX guidelines</Link>, and Figma{' '}
            <Link href="#resources">resources</Link> to reduce the time needed to get from project inception to
            wireframe and prototype.
          </p>
        </article>
        <article>
          <h3>For developers</h3>
          <p>
            Integrate with our system to <Link href="#developing">start developing</Link>. Use our accessible
            and responsive <Link href="#react">React components</Link> to quickly create high quality interfaces.
          </p>
        </article>
      </div>
    </section>
  );
}
