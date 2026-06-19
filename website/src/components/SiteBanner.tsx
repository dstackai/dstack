import Icon from '@cloudscape-design/components/icon';
import { BLOG_URL } from '../routes';

// Top announcement banner, mirroring the one on the MkDocs docs site. It sits above the top
// nav; the two stick to the top together (see .site-header). Update the copy/href here when
// the announcement changes.
const BANNER_TEXT = 'Infrastructure orchestration is an agent skill';
const BANNER_HREF = `${BLOG_URL}/agentic-orchestration/`;

export function SiteBanner() {
  return (
    <aside className="site-banner">
      <a className="site-banner__link" href={BANNER_HREF}>
        {BANNER_TEXT}
        <span className="site-banner__arrow">
          <Icon name="arrow-right" />
        </span>
      </a>
    </aside>
  );
}
