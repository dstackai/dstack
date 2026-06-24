import { useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Button from '@cloudscape-design/components/button';
import Icon from '@cloudscape-design/components/icon';
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
// categories are listed individually (Case studies / Blog) to mirror the docs
// header tabs — no "Resources" dropdown.
const audienceNavItems: Array<{ label: string; href: string }> = [
  { label: 'Docs', href: DOCS_URL },
  { label: 'Case studies', href: `${BLOG_URL}/case-studies/` },
  { label: 'Blog', href: BLOG_URL },
];

type ProductLink = { id: string; text: string; secondaryText: string; href: string; external?: boolean };

// The three products. Reused by the standalone "Products" top-nav hover menu and the mobile
// nav's "Products" section.
const products: ProductLink[] = [
  { id: 'open-source', text: 'dstack', secondaryText: 'The open-source control plane that works across clouds, Kubernetes, and on-prem.', href: docsUrl('installation') },
  { id: 'sky-product', text: 'dstack Sky', secondaryText: 'Access GPU marketplace, or bring your own clouds. Hosted by us.', href: 'https://sky.dstack.ai', external: true },
  { id: 'enterprise', text: 'dstack Enterprise', secondaryText: 'Self-hosted with SSO, air-gapped setup, dedicated support, and more.', href: 'https://calendly.com/dstackai/discovery-call', external: true },
];

// Items for the mobile slide-out navigation. The blog categories are top-level links (mirroring
// the flattened desktop nav), not a "Resources" section.
const mobileNavigationItems: SideNavigationProps.Item[] = [
  {
    type: 'section',
    text: 'Products',
    defaultExpanded: true,
    items: products.map((p): SideNavigationProps.Item => ({
      type: 'link',
      text: p.text,
      href: p.href,
      ...(p.external ? { external: true, externalIconAriaLabel } : {}),
    })),
  },
  { type: 'link', text: 'Docs', href: DOCS_URL },
  { type: 'link', text: 'Case studies', href: `${BLOG_URL}/case-studies/` },
  { type: 'link', text: 'Blog', href: BLOG_URL },
  { type: 'link', text: 'GitHub', href: dstackGithubUrl, external: true, externalIconAriaLabel },
  { type: 'link', text: 'dstack Sky', href: 'https://sky.dstack.ai', external: true, externalIconAriaLabel },
];

// Standalone "Products" top-nav menu. The popup opens on hover (and on keyboard focus) and
// closes once the pointer/focus leaves both the trigger and the popup. The trigger reads like
// the plain text links beside it — no dropdown caret. A short close delay (hover-intent, below)
// lets the pointer cross the gap from trigger to popup without the menu dropping.
function ProductsHoverMenu() {
  const [open, setOpen] = useState(false);
  // Hover-intent: leaving the trigger schedules a close, but re-entering the wrapper (e.g. moving
  // onto the popup, which is a child) cancels it — so the small gap between trigger and popup
  // doesn't drop the menu.
  const closeTimer = useRef<number | undefined>(undefined);
  const openMenu = () => {
    window.clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const scheduleClose = () => {
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => setOpen(false), 150);
  };

  return (
    <div
      className="site-hover-menu"
      onMouseEnter={openMenu}
      onMouseLeave={scheduleClose}
      onFocus={openMenu}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setOpen(false);
        }
      }}
    >
      <button type="button" className="site-menu-button site-hover-menu__trigger" aria-haspopup="true" aria-expanded={open}>
        Products
      </button>
      {open && (
        <div className="site-hover-menu__popup" role="menu">
          {products.map(product => (
            <a
              key={product.id}
              role="menuitem"
              className="site-hover-menu__item"
              href={product.href}
              {...(product.external ? { target: '_blank', rel: 'noreferrer' } : {})}
            >
              <span className="site-hover-menu__item-title">
                {product.text}
                {product.external && <Icon name="external" />}
              </span>
              <span className="site-hover-menu__item-desc">{product.secondaryText}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

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
            {/* Standalone "Products" hover menu — a flat list of the three products. Sits before "Docs". */}
            <ProductsHoverMenu />
            {audienceNavItems.map(item => (
              <a key={item.label} className="site-menu-link" href={item.href}>
                {item.label}
              </a>
            ))}
            {/* Theme toggle sits between the text links and the GitHub button on large screens; on
               tablet/mobile it moves to the footer (the whole nav collapses into the burger menu). */}
            <ThemeToggle theme={theme} onToggle={onToggleTheme} className="theme-toggle--header" />
            <Button
              variant="primary"
              href={dstackGithubUrl}
              target="_blank"
              iconAlign="right"
              iconName="external"
              style={menuButtonStyle}
            >
              GitHub
            </Button>
            <Button
              href="https://sky.dstack.ai"
              target="_blank"
              iconAlign="right"
              iconName="external"
              style={menuButtonStyle}
            >
              dstack Sky
            </Button>
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
