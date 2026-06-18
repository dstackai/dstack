import Button from '@cloudscape-design/components/button';
import Link from '@cloudscape-design/components/link';
import { PRIVACY_URL, TERMS_URL } from '../routes';
import { ThemeMode } from '../theme';

// Global footer with the theme toggle, copyright, and legal links. On the home
// page it carries an extra gradient (.site-footer--home).
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
      <div className="site-frame footer-inner">
        <div className="footer-left">
          <Button
            className="footer-theme-toggle"
            variant="icon"
            iconName="light-dark"
            ariaLabel={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
            onClick={onToggleTheme}
          />
          <span className="footer-copyright">© 2026, dstack Inc. All rights reserved.</span>
        </div>
        <nav aria-label="Footer">
          <Link href={TERMS_URL}>Terms of service</Link>
          <Link href={PRIVACY_URL}>Privacy policy</Link>
        </nav>
      </div>
    </footer>
  );
}
