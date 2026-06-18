import { Navigate, createBrowserRouter } from 'react-router-dom';
import { App } from './App';
import { HomePage } from './pages/Home';
import { OldPage } from './pages/Old';
import { ROUTES } from './routes';

// Single data router. In production this app owns only `/` (the landing) — docs and blog
// are served by MkDocs on the same origin. `/old` is kept as a template for future product
// pages: reachable in dev, and harmless in production (MkDocs serves unknown paths). Stray
// paths redirect home.
export const router = createBrowserRouter([
  {
    element: <App />,
    children: [
      { index: true, element: <HomePage /> },
      { path: ROUTES.OLD, element: <OldPage /> },
      { path: '*', element: <Navigate to={ROUTES.HOME} replace /> },
    ],
  },
], { basename: import.meta.env.BASE_URL.replace(/\/$/, '') || '/' });
