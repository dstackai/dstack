import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The deploy path is injected via BASE_PATH (set by CI from the repo name), so nothing
// in the app hardcodes where it's hosted. Locally (dev/build/preview) it stays at root.
//
// `assetsDir` is namespaced to `website-assets/` (not Vite's default `assets/`) so the
// build can be overlaid onto the MkDocs `site/` output without colliding with MkDocs's
// own `/assets/...` tree. Public files live under `public/static/` for the same reason —
// the HTML entries provide the landing and Sky product routes on static hosting.
export default defineConfig({
  base: process.env.BASE_PATH || '/',
  plugins: [react()],
  build: {
    assetsDir: 'website-assets',
    rollupOptions: {
      input: {
        home: fileURLToPath(new URL('./index.html', import.meta.url)),
        sky: fileURLToPath(new URL('./products/sky/index.html', import.meta.url)),
      },
    },
  },
});
