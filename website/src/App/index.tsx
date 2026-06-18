import { useState } from 'react';
import { Outlet, useLocation, useOutletContext } from 'react-router-dom';
import { SiteFooter } from '../components/SiteFooter';
import { SiteNavigation } from '../components/SiteNavigation';
import { ROUTES } from '../routes';
import { useTheme } from '../theme';

// State shared from the layout down to routed pages via the router Outlet context.
// Used by the Old page (its side-nav drawer) and the top-nav trigger.
export type LayoutContext = {
  oldNavigationOpen: boolean;
  setOldNavigationOpen: (open: boolean) => void;
};

export function useLayoutContext() {
  return useOutletContext<LayoutContext>();
}

// Layout shell: persistent top navigation and footer wrapping the routed page.
export function App() {
  const { theme, toggleTheme } = useTheme();
  const { pathname } = useLocation();
  const [oldNavigationOpen, setOldNavigationOpen] = useState(true);

  const layoutContext: LayoutContext = { oldNavigationOpen, setOldNavigationOpen };

  return (
    <>
      <SiteNavigation
        oldNavigationOpen={oldNavigationOpen}
        onToggleOldNavigation={() => setOldNavigationOpen(open => !open)}
      />
      <Outlet context={layoutContext} />
      <SiteFooter home={pathname === ROUTES.HOME} theme={theme} onToggleTheme={toggleTheme} />
    </>
  );
}
