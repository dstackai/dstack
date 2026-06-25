// Central route table + cross-links to the MkDocs-served parts of the site.
//
// This app (the landing) owns only `/`. Docs and blog are served by MkDocs on the
// SAME origin in production (`/docs`, `/blog`). For standalone landing development you
// can point those links at the live site by setting VITE_DOCS_BASE, e.g.
//   VITE_DOCS_BASE=https://dstack.ai npm run dev
const SITE_BASE = (import.meta.env.VITE_DOCS_BASE ?? '').replace(/\/+$/, '');

export const ROUTES = {
  HOME: '/',
  // Kept as a template/reference for building future product pages. Reachable in dev
  // (`npm run dev` at /old); not part of the integrated production deploy (where this app
  // only owns `/` and MkDocs serves everything else).
  OLD: '/old',
} as const;

export type Route = (typeof ROUTES)[keyof typeof ROUTES];

// Cross-links into the MkDocs site (same origin unless VITE_DOCS_BASE is set).
export const DOCS_URL = `${SITE_BASE}/docs`;
export const BLOG_URL = `${SITE_BASE}/blog`;
export const TERMS_URL = `${SITE_BASE}/terms`;
export const PRIVACY_URL = `${SITE_BASE}/privacy`;

// Deep link into the docs, e.g. docsUrl('concepts/fleets') -> `${SITE_BASE}/docs/concepts/fleets`.
export const docsUrl = (path: string) => `${DOCS_URL}/${path.replace(/^\/+/, '')}`;
