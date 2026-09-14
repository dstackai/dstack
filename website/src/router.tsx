import { Navigate, createBrowserRouter } from 'react-router-dom';
import { App } from './App';
import { HomePage } from './pages/Home';
import { SkyPage } from './pages/Sky/SkyPage';
import { ROUTES } from './routes';

// The landing and product pages share one layout. Docs and blog are served by MkDocs
// on the same origin; stray paths redirect home.
export const router = createBrowserRouter([
  {
    element: <App />,
    children: [
      { index: true, element: <HomePage /> },
      { path: ROUTES.SKY, element: <SkyPage /> },
      { path: '*', element: <Navigate to={ROUTES.HOME} replace /> },
    ],
  },
], { basename: import.meta.env.BASE_URL.replace(/\/$/, '') || '/' });
