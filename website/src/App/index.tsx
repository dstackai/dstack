import { useState } from 'react';
import { Outlet, useLocation, useOutletContext } from 'react-router-dom';
import { SiteBanner } from '../components/SiteBanner';
import { SiteFooter } from '../components/SiteFooter';
import { SiteNavigation } from '../components/SiteNavigation';
import { ROUTES } from '../routes';
import { useTheme, ThemeMode } from '../theme';

// State shared from the layout down to routed pages via the router Outlet context.
// Used by the Old page (its side-nav drawer + in-content footer) and the top-nav trigger.
export type LayoutContext = {
  oldNavigationOpen: boolean;
  setOldNavigationOpen: (open: boolean) => void;
  theme: ThemeMode;
  toggleTheme: () => void;
};

export function useLayoutContext() {
  return useOutletContext<LayoutContext>();
}

// Layout shell: persistent top navigation and footer wrapping the routed page.
export function App() {
  const { theme, toggleTheme } = useTheme();
  const { pathname } = useLocation();
  const [oldNavigationOpen, setOldNavigationOpen] = useState(true);

  const layoutContext: LayoutContext = { oldNavigationOpen, setOldNavigationOpen, theme, toggleTheme };

  return (
    <>
      <div className="site-header">
        <SiteBanner />
        <SiteNavigation
          oldNavigationOpen={oldNavigationOpen}
          onToggleOldNavigation={() => setOldNavigationOpen(open => !open)}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
      </div>
      <Outlet context={layoutContext} />
      {/* The Old page renders its own footer inside the AppLayout content, so the side nav
          runs full-height beside it; every other page uses the global footer here. */}
      {pathname !== ROUTES.OLD && (
        <SiteFooter home={pathname === ROUTES.HOME} theme={theme} onToggleTheme={toggleTheme} />
      )}
    </>
  );
}
