// Dotted outline shared by the architecture diagram and the "AI-native orchestration" concept
// cards: a single rounded rect stroked with the exact 2-on / 6-off dash. Geometry, color, and
// radius live in CSS (.arch-dash / .arch-dash rect in styles.css), so it follows the element's
// rounded corners, stays crisp at any size, and takes the current text color (theme-adaptive).
export function DashedBorder() {
  return (
    <svg className="arch-dash" aria-hidden="true">
      <rect />
    </svg>
  );
}
