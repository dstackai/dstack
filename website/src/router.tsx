import { Navigate, createBrowserRouter } from 'react-router-dom';
import { App } from './App';
import { HomePage } from './pages/Home';
import { ROUTES } from './routes';

// Single data router. This app owns only `/` — docs and blog are served by MkDocs on
// the same origin. Any other path is handled by MkDocs in production; in standalone dev
// we redirect stray paths back home.
export const router = createBrowserRouter([
  {
    element: <App />,
    children: [
      { index: true, element: <HomePage /> },
      { path: '*', element: <Navigate to={ROUTES.HOME} replace /> },
    ],
  },
], { basename: import.meta.env.BASE_URL.replace(/\/$/, '') || '/' });
