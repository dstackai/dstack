// Image assets used on the landing page. Local SVGs live in /public/static; the
// architecture diagram is served from the dstack static-assets host.
import { asset } from '../asset';

export const images = {
  // Home hero artwork (light/dark variants).
  hero: {
    light: asset('/static/dstack-gpu-artwork.svg'),
    dark: asset('/static/dstack-gpu-artwork-dark.svg'),
  },
  // Architecture diagram for the "Vendor-agnostic, open-source" block.
  architecture: {
    light: 'https://dstack.ai/static-assets/static-assets/images/dstack-architecture-diagram-v11.svg',
    dark: 'https://dstack.ai/static-assets/static-assets/images/dstack-architecture-diagram-v11-dark.svg',
  },
} as const;

export type ThemedImage = { light: string; dark: string };
