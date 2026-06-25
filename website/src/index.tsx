import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import '@cloudscape-design/global-styles/index.css';
import './styles.css';
import './cloudscape-overrides.css'; // non-themeable details (hairline borders, tab colors, split-button spacing)
import './cloudscape-theme'; // applies dstack's Cloudscape design-token overrides (runs on import, before render)
import { router } from './router';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
