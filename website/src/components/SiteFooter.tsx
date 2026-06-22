import Link from '@cloudscape-design/components/link';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { ThemeToggle } from './ThemeToggle';
import { asset } from '../asset';
import { BLOG_URL, docsUrl, PRIVACY_URL, TERMS_URL } from '../routes';
import { ThemeMode } from '../theme';

type FooterLinkItem = { label: string; href: string; external?: boolean };
type FooterColumn = { heading: string; links: FooterLinkItem[] };

// Brand-area social links (single-color SVG paths drawn in currentColor), matching the
// icons configured for the MkDocs site footer.
const socialLinks: { label: string; href: string; path: string }[] = [
  {
    label: 'GitHub',
    href: 'https://github.com/dstackai/dstack',
    path: 'M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12',
  },
  {
    label: 'Discord',
    href: 'https://discord.gg/u8SmfwPpMd',
    path: 'M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z',
  },
  {
    label: 'X',
    href: 'https://x.com/dstackai',
    path: 'M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z',
  },
  {
    label: 'LinkedIn',
    href: 'https://www.linkedin.com/company/dstackai',
    path: 'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z',
  },
];

// Link columns for the footer, mirroring the dstack.ai site footer. Doc/blog/legal links
// resolve through the route table (same origin in production, VITE_DOCS_BASE in dev).
const footerColumns: FooterColumn[] = [
  {
    heading: 'Documentation',
    links: [
      { label: 'Getting started', href: docsUrl('installation') },
      { label: 'Concepts', href: docsUrl('concepts/backends/') },
      { label: 'Guides', href: docsUrl('guides/protips/') },
      { label: 'Reference', href: docsUrl('reference/dstack.yml/dev-environment/') },
    ],
  },
  {
    heading: 'Examples',
    links: [
      { label: 'Training', href: docsUrl('examples/training/trl/') },
      { label: 'Clusters', href: docsUrl('examples/clusters/aws/') },
      { label: 'Inference', href: docsUrl('examples/inference/sglang/') },
      { label: 'Models', href: docsUrl('examples/models/deepseek-v4/') },
      { label: 'Accelerators', href: docsUrl('examples/accelerators/amd/') },
    ],
  },
  {
    heading: 'Community',
    links: [
      { label: 'GitHub', href: 'https://github.com/dstackai/dstack', external: true },
      { label: 'Discord', href: 'https://discord.gg/u8SmfwPpMd', external: true },
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'Blog', href: BLOG_URL },
      { label: 'Talk to us', href: 'https://calendly.com/dstackai/discovery-call', external: true },
      { label: 'Terms of service', href: TERMS_URL },
      { label: 'Privacy policy', href: PRIVACY_URL },
    ],
  },
];

// Global footer: a brand block (logo + social) reserving the leading ~1.5 columns,
// then the multi-column link grid, with the theme toggle and copyright in a
// divider-separated bottom bar. On the home page it carries an extra gradient
// (.site-footer--home).
export function SiteFooter({
  home,
  theme,
  onToggleTheme,
}: {
  home: boolean;
  theme: ThemeMode;
  onToggleTheme: () => void;
}) {
  return (
    <footer className={`site-footer ${home ? 'site-footer--home' : ''}`}>
      <div className="site-frame footer-content">
        <div className="footer-top">
          <div className="footer-brand">
            <a className="footer-brand__logo" href={asset('')} aria-label="dstack home">
              <img src={asset('/static/logo-notext.svg')} alt="" />
              <span>dstack</span>
            </a>
            <ul className="footer-channels" aria-label="Community links">
              {socialLinks.map(social => (
                <li key={social.label}>
                  <a
                    className="footer-channel-link"
                    href={social.href}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={social.label}
                  >
                    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                      <path d={social.path} fill="currentColor" />
                    </svg>
                  </a>
                </li>
              ))}
            </ul>
          </div>
          <nav className="footer-links" aria-label="Footer">
            {footerColumns.map(column => (
              <div className="footer-col" key={column.heading}>
                <h2 className="footer-col__heading">{column.heading}</h2>
                <SpaceBetween size="xs">
                  {column.links.map(link => (
                    <Link key={link.label} href={link.href} external={link.external}>
                      {link.label}
                    </Link>
                  ))}
                </SpaceBetween>
              </div>
            ))}
          </nav>
        </div>
        <div className="footer-bar">
          <span className="footer-copyright">© 2026, dstack Inc. All rights reserved.</span>
          {/* After the copyright; shown only on tablet/mobile (on large screens the toggle lives in
              the header nav). */}
          <ThemeToggle theme={theme} onToggle={onToggleTheme} className="theme-toggle--footer" />
        </div>
      </div>
    </footer>
  );
}
