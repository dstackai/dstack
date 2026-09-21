import { Fragment, ReactNode, useRef, useState } from 'react';
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
const externalIconAriaLabel = 'External link icon';

const BoxGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" /><path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" />
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
  external?: boolean;
};

// The products. products[0] (open-source) is featured at the top of the "Products" menu; the rest
// follow as rows. Reused by the standalone top-nav hover menu and the mobile nav's "Products"
// section.
// NOTE: the descriptions are duplicated in GetStartedSection.tsx (the product list) and
// mkdocs/overrides/header-2.html — keep all three in sync.
const products: ProductLink[] = [
  { id: 'open-source', text: 'dstack', secondaryText: 'The open-source control plane for AI-native orchestration.', href: asset(ROUTES.HOME), icon: <BoxGlyph />, badge: 'Self-hosted' },
  { id: 'factory', text: 'dstack Factory', secondaryText: 'A complete software stack for AI labs, inference providers, and data centers.', href: 'https://calendly.com/dstackai/discovery-call', icon: <LayersGlyph />, badge: 'Self-hosted', external: true },
  { id: 'sky-product', text: 'dstack Sky', secondaryText: 'A GPU cloud marketplace. Rent GPUs on demand or bring your own compute.', href: asset(ROUTES.SKY), icon: <CloudGlyph />, badge: 'Hosted by us' },
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
      external: p.external,
      externalIconAriaLabel,
    })),
  },
  { type: 'link', text: 'Docs', href: DOCS_URL },
  { type: 'link', text: 'Case studies', href: `${BLOG_URL}/case-studies/` },
  { type: 'link', text: 'Blog', href: BLOG_URL },
];

function ProductsHoverMenu({ selectedProductId }: { selectedProductId: string }) {
  const [open, setOpen] = useState(false);
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

  return (
    <div
      className="site-hover-menu"
      onMouseEnter={openMenu}
      onMouseLeave={event => scheduleClose(event.currentTarget)}
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
              className={`gs-opt gs-opt--feat${selectedProductId === products[0].id ? ' gs-opt--on' : ''}`}
              role="menuitem"
              href={products[0].href}
              aria-current={selectedProductId === products[0].id ? 'page' : undefined}
            >
              <span className="gs-opt__ic">{products[0].icon}</span>
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
                  className={`gs-opt gs-opt--row${selectedProductId === product.id ? ' gs-opt--on' : ''}`}
                  href={product.href}
                  aria-current={selectedProductId === product.id ? 'page' : undefined}
                  target={product.external ? '_blank' : undefined}
                  rel={product.external ? 'noreferrer' : undefined}
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
            activeHref={asset(isSkyPage ? ROUTES.SKY : ROUTES.HOME)}
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
