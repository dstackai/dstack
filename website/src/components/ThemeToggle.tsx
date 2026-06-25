import { ThemeMode } from '../theme';

// Pill switch + crescent moon, matching the dstack control-plane app's theme toggle
// (frontend/src/layouts/AppLayout/themeIcons.tsx + assets/icons/theme.svg). The "on" (dark) state
// — filled track, thumb slid right — is driven entirely by CSS via [data-theme="dark"] (set in
// theme.ts); this component just renders the markup. `className` lets the header and footer
// instances be shown at different breakpoints (see .theme-toggle--header / --footer in styles.css).
export function ThemeToggle({
  theme,
  onToggle,
  className = '',
}: {
  theme: ThemeMode;
  onToggle: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={`theme-toggle ${className}`.trim()}
      aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
      onClick={onToggle}
    >
      <span className="theme-toggle__track" aria-hidden="true">
        <span className="theme-toggle__thumb" />
      </span>
      <svg className="theme-toggle__moon" viewBox="0 0 16 16" width="16" height="16" fill="none" aria-hidden="true">
        <path
          d="M12.8166 9.79921C12.8417 9.75608 12.7942 9.70771 12.7497 9.73041C11.9008 10.164 10.9392 10.4085 9.92054 10.4085C6.48046 10.4085 3.69172 7.61979 3.69172 4.17971C3.69172 3.16099 3.93628 2.19938 4.36989 1.3504C4.39259 1.30596 4.34423 1.25842 4.3011 1.28351C2.44675 2.36242 1.2002 4.37123 1.2002 6.67119C1.2002 10.1113 3.98893 12.9 7.42901 12.9C9.72893 12.9 11.7377 11.6535 12.8166 9.79921Z"
          fill="currentColor"
          stroke="currentColor"
          strokeWidth="2"
        />
      </svg>
    </button>
  );
}
