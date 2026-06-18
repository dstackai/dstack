import { Outlet, useLocation } from 'react-router-dom';
import { SiteFooter } from '../components/SiteFooter';
import { SiteNavigation } from '../components/SiteNavigation';
import { ROUTES } from '../routes';
import { useTheme } from '../theme';

// Layout shell: persistent top navigation and footer wrapping the routed page.
export function App() {
  const { theme, toggleTheme } = useTheme();
  const { pathname } = useLocation();

  return (
    <>
      <SiteNavigation />
      <Outlet />
      <SiteFooter home={pathname === ROUTES.HOME} theme={theme} onToggleTheme={toggleTheme} />
    </>
  );
}
