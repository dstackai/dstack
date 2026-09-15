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

// Layout shell: persistent top navigation and footer wrapping the routed page.
export function App() {
  const { theme, toggleTheme } = useTheme();
  const { pathname } = useLocation();
  const isSkyPage = pathname.replace(/\/$/, '') === ROUTES.SKY;

  useEffect(() => {
    const title = isSkyPage
      ? 'dstack Sky — The AI cloud with AI-native orchestration'
      : 'dstack — The orchestration stack for AI infrastructure';
    const description = isSkyPage
      ? 'A heterogeneous AI cloud with NVIDIA Blackwell, Hopper, and AMD Instinct GPUs. Access on-demand instances, spot capacity, and reserved clusters.'
      : 'dstack is a unified control plane for GPU provisioning and orchestration that works with any GPU cloud, Kubernetes, or on-prem clusters.';
    const url = isSkyPage ? 'https://dstack.ai/products/sky/' : 'https://dstack.ai/';
    document.title = title;
    document.querySelector('link[rel="canonical"]')?.setAttribute('href', url);
    document.querySelector('meta[property="og:url"]')?.setAttribute('content', url);
    for (const selector of ['meta[property="og:title"]', 'meta[name="twitter:title"]']) {
      document.querySelector(selector)?.setAttribute('content', title);
    }
    for (const selector of ['meta[name="description"]', 'meta[property="og:description"]', 'meta[name="twitter:description"]']) {
      document.querySelector(selector)?.setAttribute('content', description);
    }
  }, [isSkyPage]);

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
