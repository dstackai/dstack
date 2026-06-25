// Resolve a path to a file in public/ against the configured base URL, so assets work
// both at the site root (dev) and under the GitHub Pages project subpath in production.
export const asset = (path: string) => import.meta.env.BASE_URL + path.replace(/^\//, '');
