import { Fragment, ReactNode, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Button from '@cloudscape-design/components/button';
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
const CloudGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
  </svg>
);
const LayersGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z" /><path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12" /><path d="M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17" />
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
  icon: ReactNode;
  badge: string;
};

// The products. products[0] (open-source) is featured at the top of the "Products" menu; the rest
// follow as rows. Reused by the standalone top-nav hover menu and the mobile nav's "Products"
// section.
// NOTE: the descriptions are duplicated in GetStartedSection.tsx (the product list) and
// mkdocs/overrides/header-2.html — keep all three in sync.
const products: ProductLink[] = [
  { id: 'open-source', text: 'dstack', secondaryText: 'The open-source control plane for AI-native orchestration.', href: asset(ROUTES.HOME), icon: <GithubGlyph />, badge: 'Self-hosted' },
  { id: 'factory', text: 'dstack Factory', secondaryText: 'A complete software stack for AI labs, inference providers, and data centers.', href: 'https://calendly.com/dstackai/discovery-call', icon: <LayersGlyph />, badge: 'Self-hosted' },
  { id: 'sky-product', text: 'dstack Sky', secondaryText: 'An AI cloud with AI-native orchestration. Rent GPUs on demand or bring your own compute.', href: asset(ROUTES.SKY), icon: <CloudGlyph />, badge: 'Hosted by us' },
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
      external: true,
      externalIconAriaLabel,
    })),
  },
  { type: 'link', text: 'Docs', href: DOCS_URL },
  { type: 'link', text: 'Case studies', href: `${BLOG_URL}/case-studies/` },
  { type: 'link', text: 'Blog', href: BLOG_URL },
];

function ProductsHoverMenu({ selectedProductId }: { selectedProductId: string }) {
  const [open, setOpen] = useState(false);
  const [hoveredProductId, setHoveredProductId] = useState<string | null>(null);
  const activeProductId = hoveredProductId ?? selectedProductId;
  const closeTimer = useRef<number | undefined>(undefined);
  const openMenu = () => {
    window.clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const scheduleClose = (menu: HTMLDivElement) => {
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => {
      if (!menu.querySelector(':focus-visible')) setOpen(false);
    }, 150);
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
      onMouseLeave={event => {
        setHoveredProductId(null);
        scheduleClose(event.currentTarget);
      }}
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
        <div className="site-products-menu">
          <div className="gs-rail" role="menu">
            <div className="gs-rail__group">Self-hosted</div>
            <a
              className={`gs-opt gs-opt--feat${activeProductId === products[0].id ? ' gs-opt--on' : ''}`}
              role="menuitem"
              href={products[0].href}
              onMouseEnter={() => setHoveredProductId(products[0].id)}
              target="_blank"
              rel="noreferrer"
            >
              <span className="gs-opt__icwrap">
                <span className="gs-opt__ic"><GithubGlyph /></span>
                {stars !== null && (
                  <span className="gs-opt__stars" aria-label={`${stars} GitHub stars`}>{formatStars(stars)}</span>
                )}
              </span>
              <span className="gs-opt__body">
                <span className="gs-opt__name">{products[0].text}</span>
                <span className="gs-opt__desc">{products[0].secondaryText}</span>
              </span>
            </a>
            {products.slice(1).map((product, index) => (
              <Fragment key={product.id}>
                {product.badge !== products[index].badge && <div className="gs-rail__group">{product.badge}</div>}
                <a
                  role="menuitem"
                  className={`gs-opt gs-opt--row${activeProductId === product.id ? ' gs-opt--on' : ''}`}
                  href={product.href}
                  onMouseEnter={() => setHoveredProductId(product.id)}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className="gs-opt__ic">{product.icon}</span>
                  <span className="gs-opt__body">
                    <span className="gs-opt__name">{product.text}</span>
                    <span className="gs-opt__desc">{product.secondaryText}</span>
                  </span>
                </a>
              </Fragment>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function SiteNavigation({
  theme,
  onToggleTheme,
}: {
  theme: ThemeMode;
  onToggleTheme: () => void;
}) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

  const isSkyPage = pathname.replace(/\/$/, '') === ROUTES.SKY;
  const menuAction = isSkyPage
    ? { text: 'Sign in', href: 'https://sky.dstack.ai/' }
    : { text: 'GitHub', href: dstackGithubUrl };

  const go = (to: string) => {
    navigate(to);
    setMobileNavigationOpen(false);
  };

  return (
    <header className={`site-nav site-nav--home ${mobileNavigationOpen ? 'site-nav--mobile-open' : ''}`}>
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
        <button
          className="site-logo"
          aria-label="dstack home"
          onClick={() => go(ROUTES.HOME)}
        >
          <img src={asset('/static/logo-notext.svg')} alt="" />
          <span>dstack</span>
        </button>
        <nav className="site-menu" aria-label="Global">
          <SpaceBetween direction="horizontal" size="l" alignItems="center">
            {/* Standalone "Products" hover menu — a flat list of the three products. Sits before "Docs". */}
            <ProductsHoverMenu selectedProductId={isSkyPage ? 'sky-product' : 'open-source'} />
            {audienceNavItems.map(item => (
              <a key={item.label} className="site-menu-link" href={item.href}>
                {item.label}
              </a>
            ))}
            <ThemeToggle theme={theme} onToggle={onToggleTheme} className="theme-toggle--header" />
            <Button
              href={menuAction.href}
              target="_blank"
              iconAlign="right"
              iconName="external"
              style={menuButtonStyle}
            >
              {menuAction.text}
            </Button>
          </SpaceBetween>
        </nav>
        <div className="site-mobile-spacer" aria-hidden="true" />
      </div>
      {mobileNavigationOpen && (
        <div className="site-mobile-navigation" id="site-mobile-navigation">
          <SideNavigation
            activeHref={pathname}
            items={[
              ...mobileNavigationItems,
              { type: 'link', ...menuAction, external: true, externalIconAriaLabel },
            ]}
            onFollow={() => setMobileNavigationOpen(false)}
          />
        </div>
      )}
    </header>
  );
}
