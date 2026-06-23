import { BLOG_URL } from '../routes';

// Top announcement banner, mirroring the one on the MkDocs docs site. It sits above the top
// nav; the two stick to the top together (see .site-header). Update the copy/href here when
// the announcement changes.
const BANNER_TEXT = 'The state of heterogeneous AI compute in 2026';
const BANNER_HREF = `${BLOG_URL}/state-of-heterogeneous-compute-2026/`;

export function SiteBanner() {
  return (
    <aside className="site-banner">
      <a className="site-banner__link" href={BANNER_HREF}>
        {BANNER_TEXT}
        {/* Thin, accurate arrow (shaft + head) — lighter than Cloudscape's filled chevron. */}
        <svg
          className="site-banner__arrow"
          viewBox="0 0 24 24"
          width="17"
          height="17"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M4 12h15" />
          <path d="m12.5 5.5 6.5 6.5-6.5 6.5" />
        </svg>
      </a>
    </aside>
  );
}
