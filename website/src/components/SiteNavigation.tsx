import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Button from '@cloudscape-design/components/button';
import ButtonDropdown, { ButtonDropdownProps } from '@cloudscape-design/components/button-dropdown';
import SideNavigation, { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { asset } from '../asset';
import { BLOG_URL, DOCS_URL, ROUTES, docsUrl } from '../routes';

const dstackGithubUrl = 'https://github.com/dstackai/dstack';
const externalIconAriaLabel = 'External link icon';

const transparentButton = {
  root: { background: { default: 'transparent', hover: 'transparent', active: 'transparent' } },
};

// Primary links in the desktop top navigation. Documentation and Blog are served by
// MkDocs on the same origin, so they are plain links (full-page navigations).
const audienceNavItems: Array<{ label: string; href: string }> = [
  { label: 'Documentation', href: DOCS_URL },
  { label: 'Blog', href: BLOG_URL },
];

// "Get started" dropdown items, grouped by hosting model. secondaryText is shown under each label.
const productDropdownItems: ButtonDropdownProps.Items = [
  {
    text: 'Self-hosted',
    items: [
      { id: 'open-source', text: 'Open-source', secondaryText: 'Install the open-source version', href: docsUrl('installation'), external: true, externalIconAriaLabel },
      { id: 'enterprise', text: 'dstack Enterprise', secondaryText: 'Talk to us', href: 'https://calendly.com/dstackai/discovery-call', external: true, externalIconAriaLabel },
    ],
  },
  {
    text: 'Hosted by dstack',
    items: [
      { id: 'sky', text: 'dstack Sky', secondaryText: 'Sign up for dstack Sky', href: 'https://sky.dstack.ai', external: true, externalIconAriaLabel },
    ],
  },
];

// Items for the mobile slide-out navigation.
const mobileNavigationItems: SideNavigationProps.Item[] = [
  { type: 'link', text: 'Documentation', href: DOCS_URL },
  { type: 'link', text: 'Blog', href: BLOG_URL },
  { type: 'link', text: 'GitHub', href: dstackGithubUrl, external: true, externalIconAriaLabel },
  {
    type: 'section',
    text: 'Get started',
    defaultExpanded: true,
    items: [
      { type: 'link', text: 'Open-source', href: docsUrl('installation'), external: true, externalIconAriaLabel },
      { type: 'link', text: 'dstack Sky', href: 'https://sky.dstack.ai', external: true, externalIconAriaLabel },
      { type: 'link', text: 'dstack Enterprise', href: 'https://calendly.com/dstackai/discovery-call', external: true, externalIconAriaLabel },
    ],
  },
];

// Global top navigation.
export function SiteNavigation() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

  const isHome = pathname === ROUTES.HOME;

  const go = (to: string) => {
    navigate(to);
    setMobileNavigationOpen(false);
  };

  // Scroll to the "Get started" section, navigating home first if we're on another page.
  const scrollToResources = () => {
    const target = document.getElementById('resources');
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }

    go(ROUTES.HOME);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        document.getElementById('resources')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  };

  return (
    <header className={`site-nav ${isHome ? 'site-nav--home' : ''} ${mobileNavigationOpen ? 'site-nav--mobile-open' : ''}`}>
      <div className="site-nav__inner">
        <div className="site-mobile-trigger">
          <Button
            variant="icon"
            iconName={mobileNavigationOpen ? 'close' : 'menu'}
            ariaLabel={mobileNavigationOpen ? 'Close navigation' : 'Open navigation'}
            ariaExpanded={mobileNavigationOpen}
            ariaControls="site-mobile-navigation"
            onClick={() => setMobileNavigationOpen(open => !open)}
          />
        </div>
        <button className="site-logo" aria-label="dstack home" onClick={() => go(ROUTES.HOME)}>
          <img src={asset('/static/logo-notext.svg')} alt="" />
          <span>dstack</span>
        </button>
        <nav className="site-menu" aria-label="Global">
          <SpaceBetween direction="horizontal" size="s" alignItems="center">
            {audienceNavItems.map(item => (
              <a key={item.label} className="site-menu-link" href={item.href}>
                {item.label}
              </a>
            ))}
            <Button
              href={dstackGithubUrl}
              target="_blank"
              iconAlign="right"
              iconName="external"
              style={transparentButton}
            >
              GitHub
            </Button>
            <ButtonDropdown
              className="site-get-started"
              items={productDropdownItems}
              ariaLabel="Get started options"
              mainAction={{ text: 'Get started', onClick: scrollToResources }}
              variant="primary"
            />
          </SpaceBetween>
        </nav>
        <div className="site-mobile-spacer" aria-hidden="true" />
      </div>
      {mobileNavigationOpen && (
        <div className="site-mobile-navigation" id="site-mobile-navigation">
          <SideNavigation
            activeHref={pathname}
            items={mobileNavigationItems}
            onFollow={() => setMobileNavigationOpen(false)}
          />
        </div>
      )}
    </header>
  );
}
