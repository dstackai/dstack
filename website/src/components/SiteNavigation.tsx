import { useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Button from '@cloudscape-design/components/button';
import ButtonDropdown, { ButtonDropdownProps } from '@cloudscape-design/components/button-dropdown';
import SideNavigation, { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { menuButtonStyle } from '../cloudscape-theme';
import { asset } from '../asset';
import { BLOG_URL, DOCS_URL, ROUTES, docsUrl } from '../routes';

const dstackGithubUrl = 'https://github.com/dstackai/dstack';
const externalIconAriaLabel = 'External link icon';

// Primary links in the desktop top navigation (plain same-origin MkDocs links).
const audienceNavItems: Array<{ label: string; href: string }> = [
  { label: 'Documentation', href: DOCS_URL },
];

// "Resources" top-nav dropdown: the blog landing plus its two main categories (all
// same-origin MkDocs pages).
const resourcesDropdownItems: ButtonDropdownProps.Items = [
  {
    id: 'case-studies',
    text: 'Case studies',
    secondaryText: 'How AI teams run training and inference with dstack.',
    href: `${BLOG_URL}/case-studies/`,
  },
  {
    id: 'benchmarks',
    text: 'Benchmarks',
    secondaryText: 'Comparing hardware, inference engines, and deployment setups for AI.',
    href: `${BLOG_URL}/benchmarks/`,
  },
  {
    id: 'blog',
    text: 'Blog',
    secondaryText: 'Major releases, industry reports, and product updates.',
    href: BLOG_URL,
  },
];

// "Resources" dropdown that opens on hover and stays open while the cursor is over the
// trigger OR the popup (the popup renders inside this wrapper, so hovering it still counts as
// hovering the wrapper). Cloudscape's ButtonDropdown is click-only, so we open/close it by
// reading aria-expanded and synthesizing a click on the trigger — click and keyboard keep
// working unchanged. A short close delay bridges the gap between trigger and popup so moving
// the cursor across it doesn't dismiss the menu. Desktop top-nav only (mobile uses SideNavigation).
function ResourcesHoverMenu() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<number | undefined>(undefined);

  const trigger = () => wrapRef.current?.querySelector('button') ?? null;
  const isOpen = () => trigger()?.getAttribute('aria-expanded') === 'true';
  const cancelClose = () => {
    if (closeTimer.current !== undefined) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = undefined;
    }
  };
  const openNow = () => {
    cancelClose();
    if (!isOpen()) trigger()?.click();
  };
  const closeSoon = () => {
    cancelClose();
    closeTimer.current = window.setTimeout(() => {
      if (isOpen()) trigger()?.click();
    }, 140);
  };

  return (
    <div ref={wrapRef} className="site-menu-dropdown-wrap" onMouseEnter={openNow} onMouseLeave={closeSoon}>
      <ButtonDropdown className="site-menu-dropdown" items={resourcesDropdownItems} ariaLabel="Resources menu">
        Resources
      </ButtonDropdown>
    </div>
  );
}

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

// Items for the mobile slide-out navigation.
const mobileNavigationItems: SideNavigationProps.Item[] = [
  { type: 'link', text: 'Documentation', href: DOCS_URL },
  // The desktop "Resources" dropdown becomes an expandable section on mobile (SideNavigation
  // has no popups), matching the "Get started" section pattern below.
  {
    type: 'section',
    text: 'Resources',
    defaultExpanded: true,
    items: [
      { type: 'link', text: 'Case studies', href: `${BLOG_URL}/case-studies/` },
      { type: 'link', text: 'Benchmarks', href: `${BLOG_URL}/benchmarks/` },
      { type: 'link', text: 'Blog', href: BLOG_URL },
    ],
  },
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
}: {
  oldNavigationOpen: boolean;
  onToggleOldNavigation: () => void;
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
    <header className={`site-nav ${isHome ? 'site-nav--home' : ''} ${mobileNavigationOpen ? 'site-nav--mobile-open' : ''}`}>
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
            {/* Resources dropdown (Case studies / Benchmarks / Blog), styled to read like the
               plain text menu links above; opens on hover. */}
            <ResourcesHoverMenu />
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
