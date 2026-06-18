// dstack's visual customization of Cloudscape, expressed through the official theming
// API (@cloudscape-design/components/theming). We only override design tokens here — no
// CSS reaching into Cloudscape's internal (hashed) class/variable names — so this stays
// on the supported path and survives Cloudscape upgrades. Applied once before the first
// render (see index.tsx), which is the supported way to avoid a flash of the base theme.
import { applyTheme, Theme } from '@cloudscape-design/components/theming';
import type { ButtonProps } from '@cloudscape-design/components/button';

// Mirrors the --cs-* palette in styles.css (light/dark). Token values accept either a
// single string or a { light, dark } pair, which Cloudscape maps to its color modes.
const TEXT = { light: '#16191f', dark: '#f2f3f3' }; // body text color
const SURFACE = { light: '#ffffff', dark: '#0f141d' }; // page background — used as the label color on filled buttons
// Hover states, light + theme-aware: filled (primary) buttons shift to a slightly softer
// shade; outlined (normal) buttons, cards, and dropdown items all share one faint tint
// (--cs-hover, defined per theme in styles.css) so every interactive surface hovers alike.
const HOVER_FILL = 'var(--cs-btn-hover)'; // filled-button hover fill (defined per theme in styles.css; shared with the split-button override)
const FONT = 'var(--font-base)'; // single source of truth: the Geist stack defined in styles.css

const tokens = {
  // Typography: render Cloudscape components in Geist (replaces the hashed-token CSS
  // override that used to live in styles.css). Monospace is left as-is for code.
  fontFamilyBase: FONT,
  fontFamilyHeading: FONT,
  fontFamilyDisplay: FONT,

  // Square corners everywhere, including buttons. (Focus-ring radii are left untouched.)
  borderRadiusButton: '0px',
  borderRadiusContainer: '0px',
  borderRadiusInput: '0px',
  borderRadiusDropdown: '0px',
  borderRadiusItem: '0px',
  borderRadiusBadge: '0px',
  borderRadiusAlert: '0px',
  borderRadiusPopover: '0px',
  borderRadiusTiles: '0px',
  borderRadiusCardDefault: '0px',
  borderRadiusCardEmbedded: '0px',
  borderRadiusActionCardDefault: '0px',
  borderRadiusActionCardEmbedded: '0px',
  borderRadiusFlashbar: '0px',
  borderRadiusDropzone: '0px',
  borderRadiusTutorialPanelItem: '0px',
  borderRadiusStatusIndicator: '0px',
  borderRadiusToken: '0px',

  // Hairline borders on structural controls. Icon stroke widths (borderWidthIcon*) are
  // intentionally left alone — those drive icon rendering, not container borders.
  borderWidthButton: '0.5px',
  borderWidthField: '0.5px',
  borderWidthDropdown: '0.5px',
  borderWidthPopover: '0.5px',
  borderWidthCard: '0.5px',

  // Neutral borders/dividers take the text color instead of gray. Semantic borders
  // (status, badges, selected/focused) keep their defaults so they still read as such.
  colorBorderDividerDefault: TEXT,
  colorBorderDividerSecondary: TEXT,
  colorBorderInputDefault: TEXT,
  colorBorderControlDefault: TEXT,
  colorBorderContainerTop: TEXT,
  colorBorderDropdownContainer: TEXT,
  colorBorderPopover: TEXT,
  colorBorderLayout: TEXT,
  colorBorderCard: TEXT,
  colorBorderDialog: TEXT,
  colorBorderExpandableSectionDefault: TEXT,
  // Dropdown menu items: no outline box on the hovered/focused row; the cue is a faint
  // background tint (matching the cards/buttons) via --cs-hover.
  colorBorderDropdownItemHover: 'transparent',
  colorBorderDropdownItemFocused: 'transparent',
  colorBackgroundDropdownItemHover: 'var(--cs-hover)',

  // Primary button: filled in the text color, with the label in the surface color.
  colorBackgroundButtonPrimaryDefault: TEXT,
  colorBackgroundButtonPrimaryHover: HOVER_FILL,
  colorBackgroundButtonPrimaryActive: HOVER_FILL,
  colorBorderButtonPrimaryDefault: TEXT,
  colorBorderButtonPrimaryHover: HOVER_FILL,
  colorBorderButtonPrimaryActive: HOVER_FILL,
  colorTextButtonPrimaryDefault: SURFACE,
  colorTextButtonPrimaryHover: SURFACE,
  colorTextButtonPrimaryActive: SURFACE,

  // Normal (secondary) button: outlined, transparent by default; on hover/active a faint
  // tint (not a solid fill). Border + label stay the text color.
  colorBackgroundButtonNormalDefault: 'transparent',
  colorBackgroundButtonNormalHover: 'var(--cs-hover)',
  colorBackgroundButtonNormalActive: 'var(--cs-hover)',
  colorBorderButtonNormalDefault: TEXT,
  colorBorderButtonNormalHover: TEXT,
  colorBorderButtonNormalActive: TEXT,
  colorTextButtonNormalDefault: TEXT,
  colorTextButtonNormalHover: TEXT,
  colorTextButtonNormalActive: TEXT,
} satisfies Theme['tokens'];

// Apply on import. index.tsx imports this module for its side effect (alongside the CSS
// imports) so the theme is in place before the first render — no flash of the base theme.
applyTheme({ theme: { tokens } });

// Context-specific button padding. Cloudscape has no global button-padding token, so this
// uses the Button `style` prop (the supported per-instance route). Padding scales x and y
// proportionally: hero buttons are the most generous, main-area buttons a step below.
// (Transparent backgrounds for normal buttons are handled globally by the tokens above.)
export const heroButtonStyle: ButtonProps.Style = {
  root: { paddingBlock: '12px', paddingInline: '34px' },
};
export const mainButtonStyle: ButtonProps.Style = {
  root: { paddingBlock: '8px', paddingInline: '26px' },
};
// Top-nav buttons — slightly roomier than default but compact.
export const menuButtonStyle: ButtonProps.Style = {
  root: { paddingBlock: '7px', paddingInline: '18px' },
};
