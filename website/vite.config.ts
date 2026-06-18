import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The deploy path is injected via BASE_PATH (set by CI from the repo name), so nothing
// in the app hardcodes where it's hosted. Locally (dev/build/preview) it stays at root.
//
// `assetsDir` is namespaced to `website-assets/` (not Vite's default `assets/`) so the
// build can be overlaid onto the MkDocs `site/` output without colliding with MkDocs's
// own `/assets/...` tree. Public files live under `public/static/` for the same reason —
// after the overlay the only root file this app contributes is `index.html`.
export default defineConfig({
  base: process.env.BASE_PATH || '/',
  plugins: [react()],
  build: {
    assetsDir: 'website-assets',
  },
});
