import { ReactNode, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Button from '@cloudscape-design/components/button';
import Icon from '@cloudscape-design/components/icon';
import SideNavigation, { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { menuButtonStyle } from '../cloudscape-theme';
import { ThemeToggle } from './ThemeToggle';
import { asset } from '../asset';
import { BLOG_URL, DOCS_URL, ROUTES } from '../routes';
import { ThemeMode } from '../theme';

const dstackGithubUrl = 'https://github.com/dstackai/dstack';
const dstackGithubApiUrl = 'https://api.github.com/repos/dstackai/dstack';
const externalIconAriaLabel = 'External link icon';

// Compact star count: 1340 → "1.3k", 12000 → "12k", 980 → "980".
function formatStars(count: number): string {
  if (count < 1000) return String(count);
  const thousands = count / 1000;
  return `${thousands >= 10 ? Math.round(thousands) : Number(thousands.toFixed(1))}k`;
}

// Monochrome product glyphs for the "Products" menu (GitHub mark also doubles as the star badge).
const GithubGlyph = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
  </svg>
);
const CloudUploadGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 14.899A6 6 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 .5 8.973" />
    <path d="M12 12v8" />
    <path d="m8 16 4-4 4 4" />
  </svg>
);
const FingerprintGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 10a2 2 0 0 0-2 2c0 1.5.4 3 1 4.3" />
    <path d="M12 6.5A5.5 5.5 0 0 0 6.5 12c0 2 .4 3.5 1.1 5" />
    <path d="M12 14v3.5" />
    <path d="M15.6 8.4A5.5 5.5 0 0 1 17.5 12c0 2.2-.5 4.3-1.3 6" />
    <path d="M12 3a9 9 0 0 0-9 9" />
    <path d="M21 12a9 9 0 0 0-3-6.7" />
  </svg>
);

// Primary links in the desktop top navigation (plain same-origin MkDocs links). The blog
// categories are listed individually (Case studies / Blog) to mirror the docs
// header tabs — no "Resources" dropdown.
const audienceNavItems: Array<{ label: string; href: string }> = [
  { label: 'Docs', href: DOCS_URL },
  { label: 'Case studies', href: `${BLOG_URL}/case-studies/` },
  { label: 'Blog', href: BLOG_URL },
];

type ProductLink = {
  id: string;
  text: string;
  secondaryText: string;
  href: string;
  external?: boolean;
  icon: ReactNode;
};

// The products. products[0] (open-source) is featured at the top of the "Products" menu; the rest
// follow as rows. Reused by the standalone top-nav hover menu and the mobile nav's "Products"
// section.
const products: ProductLink[] = [
  { id: 'open-source', text: 'dstack', secondaryText: 'The open-source control plane that works across clouds, Kubernetes, and on-prem.', href: DOCS_URL, icon: <GithubGlyph /> },
  { id: 'sky-product', text: 'dstack Sky', secondaryText: 'Access GPU marketplace, or bring your own clouds. Hosted and managed by us.', href: 'https://sky.dstack.ai', external: true, icon: <CloudUploadGlyph /> },
  { id: 'enterprise', text: 'Enterprise', secondaryText: 'Self-hosted with SSO, air-gapped setup, dedicated support, and more.', href: 'https://calendly.com/dstackai/discovery-call', external: true, icon: <FingerprintGlyph /> },
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

  // GitHub star count for the open-source repo, fetched once the menu first opens. Best-effort:
  // if the API is rate-limited or errors, the badge simply doesn't render.
  const [stars, setStars] = useState<number | null>(null);
  const starsFetched = useRef(false);
  useEffect(() => {
    if (!open || starsFetched.current) return;
    starsFetched.current = true;
    fetch(dstackGithubApiUrl)
      .then(response => (response.ok ? response.json() : null))
      .then(data => {
        if (data && typeof data.stargazers_count === 'number') setStars(data.stargazers_count);
      })
      .catch(() => {});
  }, [open]);

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
        <svg className="site-hover-menu__caret" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 6.5 8 10.5 12 6.5" />
        </svg>
      </button>
      {open && (
        <div className="site-products-menu" role="menu">
          {/* Open-source featured on the brand gradient; the whole panel links to install. */}
          <a className="site-products-menu__feat" role="menuitem" href={products[0].href}>
            {stars !== null && (
              <span className="site-products-menu__gh" aria-label={`${stars} GitHub stars`}>
                <GithubGlyph />
                {formatStars(stars)}
              </span>
            )}
            <span className="site-products-menu__feat-name">{products[0].text}</span>
            <span className="site-products-menu__feat-desc">{products[0].secondaryText}</span>
            <span className="site-products-menu__feat-cta">Documentation</span>
          </a>
          <div className="site-products-menu__list">
            {products.slice(1).map(product => (
              <a
                key={product.id}
                role="menuitem"
                className="site-products-menu__row"
                href={product.href}
                {...(product.external ? { target: '_blank', rel: 'noreferrer' } : {})}
              >
                <span className="site-products-menu__ic">{product.icon}</span>
                <div className="site-products-menu__rbody">
                  <span className="site-products-menu__name">
                    {product.text}
                    {product.external && <Icon name="external" />}
                  </span>
                  <span className="site-products-menu__desc">{product.secondaryText}</span>
                </div>
              </a>
            ))}
          </div>
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
