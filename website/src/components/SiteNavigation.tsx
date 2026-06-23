import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Button from '@cloudscape-design/components/button';
import ButtonDropdown, { ButtonDropdownProps } from '@cloudscape-design/components/button-dropdown';
import SideNavigation, { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { menuButtonStyle } from '../cloudscape-theme';
import { ThemeToggle } from './ThemeToggle';
import { asset } from '../asset';
import { BLOG_URL, DOCS_URL, ROUTES, docsUrl } from '../routes';
import { ThemeMode } from '../theme';

const dstackGithubUrl = 'https://github.com/dstackai/dstack';
const externalIconAriaLabel = 'External link icon';

// Primary links in the desktop top navigation (plain same-origin MkDocs links). The blog
// categories are listed individually (Case studies / Benchmarks / Blog) to mirror the docs
// header tabs — no "Resources" dropdown.
const audienceNavItems: Array<{ label: string; href: string }> = [
  { label: 'Docs', href: DOCS_URL },
  { label: 'Case studies', href: `${BLOG_URL}/case-studies/` },
  { label: 'Benchmarks', href: `${BLOG_URL}/benchmarks/` },
  { label: 'Blog', href: BLOG_URL },
];

// "Get started" dropdown items. secondaryText is shown under each label.
const productDropdownItems: ButtonDropdownProps.Items = [
  {
    text: 'Products',
    items: [
      { id: 'open-source', text: 'dstack', secondaryText: 'The open-source control plane that works across clouds, Kubernetes, and on-prem.', href: docsUrl('installation') },
      { id: 'sky-product', text: 'dstack Sky', secondaryText: 'Access GPU marketplace, or bring your own clouds. Hosted by us.', href: 'https://sky.dstack.ai', external: true, externalIconAriaLabel },
      { id: 'enterprise', text: 'dstack Enterprise', secondaryText: 'Self-hosted with SSO, air-gapped setup, dedicated support, and more.', href: 'https://calendly.com/dstackai/discovery-call', external: true, externalIconAriaLabel },
    ],
  },
  {
    text: 'Login',
    items: [
      { id: 'sky-login', text: 'dstack Sky', href: 'https://sky.dstack.ai', external: true, externalIconAriaLabel },
    ],
  },
];

// Items for the mobile slide-out navigation. The blog categories are top-level links (mirroring
// the flattened desktop nav), not a "Resources" section.
const mobileNavigationItems: SideNavigationProps.Item[] = [
  { type: 'link', text: 'Docs', href: DOCS_URL },
  { type: 'link', text: 'Case studies', href: `${BLOG_URL}/case-studies/` },
  { type: 'link', text: 'Benchmarks', href: `${BLOG_URL}/benchmarks/` },
  { type: 'link', text: 'Blog', href: BLOG_URL },
  { type: 'link', text: 'GitHub', href: dstackGithubUrl, external: true, externalIconAriaLabel },
  {
    type: 'section',
    text: 'Get started',
    defaultExpanded: true,
    items: [
      { type: 'link', text: 'dstack', href: docsUrl('installation'), external: true, externalIconAriaLabel },
      { type: 'link', text: 'dstack Sky', href: 'https://sky.dstack.ai', external: true, externalIconAriaLabel },
      { type: 'link', text: 'dstack Enterprise', href: 'https://calendly.com/dstackai/discovery-call', external: true, externalIconAriaLabel },
    ],
  },
];

// Global top navigation. On the Old page it also renders the trigger that toggles
// that page's side navigation drawer (state owned by the App layout).
export function SiteNavigation({
  oldNavigationOpen,
  onToggleOldNavigation,
  theme,
  onToggleTheme,
}: {
  oldNavigationOpen: boolean;
  onToggleOldNavigation: () => void;
  theme: ThemeMode;
  onToggleTheme: () => void;
}) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

  const isHome = pathname === ROUTES.HOME;
  const isOldPage = pathname === ROUTES.OLD;

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
    <header className={`site-nav ${isHome ? 'site-nav--home' : ''} ${isOldPage ? 'site-nav--old' : ''} ${mobileNavigationOpen ? 'site-nav--mobile-open' : ''}`}>
      <div className="site-nav__inner">
        {isOldPage && (
          <div className="site-desktop-trigger">
            <Button
              variant="icon"
              iconName="menu"
              ariaLabel={oldNavigationOpen ? 'Close desktop version of navigation' : 'Open desktop version of navigation'}
              onClick={onToggleOldNavigation}
            />
          </div>
        )}
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
          <SpaceBetween direction="horizontal" size="l" alignItems="center">
            {audienceNavItems.map(item => (
              <a key={item.label} className="site-menu-link" href={item.href}>
                {item.label}
              </a>
            ))}
            {/* Theme toggle sits between the text links and the GitHub button on large screens; on
               tablet/mobile it moves to the footer (the whole nav collapses into the burger menu). */}
            <ThemeToggle theme={theme} onToggle={onToggleTheme} className="theme-toggle--header" />
            <Button
              href={dstackGithubUrl}
              target="_blank"
              iconAlign="right"
              iconName="external"
              style={menuButtonStyle}
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
