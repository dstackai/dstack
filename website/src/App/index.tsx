import { useEffect } from 'react';
import { Outlet, useLocation, useOutletContext } from 'react-router-dom';
import { SiteBanner } from '../components/SiteBanner';
import { SiteFooter } from '../components/SiteFooter';
import { SiteNavigation } from '../components/SiteNavigation';
import { ROUTES } from '../routes';
import { useTheme, ThemeMode } from '../theme';

export type LayoutContext = {
  theme: ThemeMode;
};

export function useLayoutContext() {
  return useOutletContext<LayoutContext>();
}

const pageMetadata: Record<string, { title: string; description: string; url: string; image: string }> = {
  [ROUTES.HOME]: {
    title: 'dstack — The orchestration stack for heterogeneous AI compute',
    description: 'dstack is a unified control plane for GPU provisioning and orchestration that works with any GPU cloud, Kubernetes, or on-prem clusters.',
    url: 'https://dstack.ai/',
    image: 'https://dstack.ai/static-assets/static-assets/images/dstack-social.png',
  },
  [ROUTES.SKY]: {
    title: 'dstack Sky — One account across GPU clouds',
    description: 'dstack Sky combines GPU capacity from multiple cloud partners with competitive pricing, unified billing, and AI-native orchestration.',
    url: 'https://dstack.ai/products/sky/',
    image: 'https://dstack.ai/static-assets/static-assets/images/dstack-sky-social.png',
  },
  [ROUTES.FACTORY]: {
    title: 'dstack Factory — A heterogeneous stack for AI token factories',
    description: 'dstack Factory is a heterogeneous orchestration stack for AI token factories. It streamlines capacity management, training, and inference deployment and optimization. It includes day-0 support for frontier open models, multi-tenancy, and billing automation.',
    url: 'https://dstack.ai/products/factory/',
    image: 'https://dstack.ai/static-assets/static-assets/images/dstack-factory-social.png',
  },
};

// Layout shell: persistent top navigation and footer wrapping the routed page.
export function App() {
  const { theme, toggleTheme } = useTheme();
  const { pathname } = useLocation();
  const metadata = pageMetadata[pathname.replace(/\/$/, '')] ?? pageMetadata[ROUTES.HOME];

  useEffect(() => {
    const { title, description, url, image } = metadata;
    document.title = title;
    document.querySelector('link[rel="canonical"]')?.setAttribute('href', url);
    document.querySelector('meta[property="og:url"]')?.setAttribute('content', url);
    for (const selector of ['meta[property="og:title"]', 'meta[name="twitter:title"]']) {
      document.querySelector(selector)?.setAttribute('content', title);
    }
    for (const selector of ['meta[name="description"]', 'meta[property="og:description"]', 'meta[name="twitter:description"]']) {
      document.querySelector(selector)?.setAttribute('content', description);
    }
    for (const selector of ['meta[property="og:image"]', 'meta[name="twitter:image"]']) {
      document.querySelector(selector)?.setAttribute('content', image);
    }
  }, [metadata]);

  const layoutContext: LayoutContext = { theme };

  return (
    <>
      <div className="site-header">
        <SiteBanner />
        <SiteNavigation theme={theme} onToggleTheme={toggleTheme} />
      </div>
      <Outlet context={layoutContext} />
      <SiteFooter theme={theme} onToggleTheme={toggleTheme} />
    </>
  );
}
