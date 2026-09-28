import { Fragment, ReactNode, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Button, { ButtonProps } from '@cloudscape-design/components/button';
import SideNavigation, { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { menuButtonStyle } from '../cloudscape-theme';
import { ThemeToggle } from './ThemeToggle';
import { asset } from '../asset';
import { BLOG_URL, DOCS_URL, ROUTES, docsUrl } from '../routes';
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
// follow as rows. Reused by the standalone top-nav menu and the mobile nav's "Products"
// section.
// Keep menu descriptions in sync with mkdocs/overrides/header-2.html.
// GetStartedSection.tsx uses a longer dstack description.
const products: ProductLink[] = [
  { id: 'open-source', text: 'dstack', secondaryText: 'A unified orchestration interface across GPU clouds, Kubernetes, VMs, and bare-metal.', href: docsUrl('installation'), icon: <BoxGlyph />, badge: 'Self-hosted' },
  { id: 'factory', text: 'dstack Factory', secondaryText: 'A multi-tenant orchestration stack for AI labs, data centers, and AI token factories.', href: asset(ROUTES.FACTORY), icon: <LayersGlyph />, badge: 'Self-hosted' },
  { id: 'sky-product', text: 'dstack Sky', secondaryText: 'Unified access to GPU clouds. Better prices and one billing.', href: asset(ROUTES.SKY), icon: <CloudGlyph />, badge: 'Hosted by us' },
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

function isProductLink(target: EventTarget | null) {
  const href = target instanceof Element ? target.closest('a')?.getAttribute('href') : null;
  return products.some(product => product.href === href);
}

function ProductsMenu({ selectedProductId }: { selectedProductId?: string }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<ButtonProps.Ref>(null);
  const focusLastItem = useRef(false);

  useEffect(() => {
    if (!open) return;
    const items = menuRef.current?.querySelectorAll<HTMLAnchorElement>('[role="menuitem"]');
    items?.[focusLastItem.current ? items.length - 1 : 0]?.focus();
    focusLastItem.current = false;
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnWindowBlur = () => setOpen(false);
    document.addEventListener('pointerdown', closeOnOutsideClick);
    window.addEventListener('blur', closeOnWindowBlur);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsideClick);
      window.removeEventListener('blur', closeOnWindowBlur);
    };
  }, [open]);

  return (
    <div
      ref={menuRef}
      className="site-products-dropdown"
      data-open={open}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setOpen(false);
        }
      }}
      onKeyDown={event => {
        if (!open) {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            focusLastItem.current = event.key === 'ArrowUp';
            setOpen(true);
          }
          return;
        }
        if (event.key === 'Escape') {
          event.preventDefault();
          event.stopPropagation();
          setOpen(false);
          triggerRef.current?.focus();
          return;
        }
        const items = Array.from(
          event.currentTarget.querySelectorAll<HTMLAnchorElement>('[role="menuitem"]'),
        );
        const index = items.indexOf(document.activeElement as HTMLAnchorElement);
        let nextIndex: number;
        switch (event.key) {
          case 'ArrowDown': nextIndex = (index + 1) % items.length; break;
          case 'ArrowUp': nextIndex = index <= 0 ? items.length - 1 : index - 1; break;
          case 'Home': nextIndex = 0; break;
          case 'End': nextIndex = items.length - 1; break;
          default: return;
        }
        event.preventDefault();
        items[nextIndex]?.focus();
      }}
    >
      <Button
        ref={triggerRef}
        variant="normal"
        style={{ root: { ...menuButtonStyle.root, paddingInline: '18px var(--products-arrow-gap)' } }}
        ariaHaspopup="menu"
        ariaExpanded={open}
        ariaControls="site-products-menu"
        onClick={() => setOpen(open => !open)}
      >
        <span className="site-products-dropdown__label">
          Products
          <svg className="site-products-dropdown__caret" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
            <path d="M4 6.5 8 10.5 12 6.5" />
          </svg>
        </span>
      </Button>
      {open && (
        <div className="site-products-menu">
          <div className="gs-rail" id="site-products-menu" role="menu" aria-label="Products">
            <div className="gs-rail__group">Self-hosted</div>
            <a
              className={`gs-opt gs-opt--feat${selectedProductId === products[0].id ? ' gs-opt--on' : ''}`}
              role="menuitem"
              tabIndex={-1}
              href={products[0].href}
              aria-current={selectedProductId === products[0].id ? 'page' : undefined}
              target={products[0].external ? '_blank' : undefined}
              rel={products[0].external ? 'noreferrer' : undefined}
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
                  tabIndex={-1}
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
  const [mobileProductHovered, setMobileProductHovered] = useState(false);
  const [mobileProductFocused, setMobileProductFocused] = useState(false);

  const isSkyPage = pathname.replace(/\/$/, '') === ROUTES.SKY;
  const isFactoryPage = pathname.replace(/\/$/, '') === ROUTES.FACTORY;
  const selectedProductId = isSkyPage ? 'sky-product' : isFactoryPage ? 'factory' : undefined;
  const menuAction = isFactoryPage
    ? { text: 'Book a demo', href: 'https://calendly.com/dstackai/discovery-call' }
    : isSkyPage
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
            onClick={() => {
              setMobileNavigationOpen(open => !open);
              setMobileProductHovered(false);
              setMobileProductFocused(false);
            }}
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
            {/* Standalone "Products" menu — a flat list of the three products. Sits before "Docs". */}
            <ProductsMenu selectedProductId={selectedProductId} />
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
        <div
          className="site-mobile-navigation"
          id="site-mobile-navigation"
          onMouseOver={event => setMobileProductHovered(isProductLink(event.target))}
          onMouseLeave={() => setMobileProductHovered(false)}
          onFocus={event => setMobileProductFocused(isProductLink(event.target))}
          onBlur={event => setMobileProductFocused(isProductLink(event.relatedTarget))}
        >
          <SideNavigation
            activeHref={mobileProductHovered || mobileProductFocused
              ? ''
              : products.find(product => product.id === selectedProductId)?.href}
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
