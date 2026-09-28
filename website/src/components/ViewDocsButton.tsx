import Button, { ButtonProps } from '@cloudscape-design/components/button';
import { mainButtonStyle } from '../cloudscape-theme';

const compactButtonStyle: ButtonProps.Style = {
  root: { ...mainButtonStyle.root, paddingInline: '14px var(--cta-padding-end)' },
};

export function ViewDocsButton({ href, style = compactButtonStyle, fullWidth }: {
  href: string;
  style?: ButtonProps['style'];
  fullWidth?: boolean;
}) {
  return (
    <span className="cta-with-arrow">
      <Button
        href={href}
        fullWidth={fullWidth}
        style={style}
      >
        <span className="cta-with-arrow__label">
          View docs
          <svg
            className="cta-with-arrow__icon"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            focusable="false"
          >
            <path d="M2 6h8M6 2l4 4-4 4" />
          </svg>
        </span>
      </Button>
    </span>
  );
}
