import {
  SquircleScene,
  type SquircleGeometryConfig,
  type SquircleLayerConfig,
  type SquircleLayerHoverContext,
} from '@dstackai/sqircle';
import '@dstackai/sqircle/style.css';
import type { ThemeMode } from '../theme';

// Live hero object, composed in the squircle constructor (@dstackai/sqircle) and pasted here.
// Layers, back → front: wireframe slab (dashed inlay) → wireframe slab → solid
// "GPU" face (dotted inlay). Layers cross-react on hover, and clicking any layer scrolls to
// Get-started. `theme` stays driven by the app toggle (the snippet hardcodes "light").
const HERO_GEOMETRY: SquircleGeometryConfig = {
  angleDegrees: 20,
};

const HERO_LAYERS: SquircleLayerConfig[] = [
  {
    id: 'layer-1',
    visible: true,
    offset: { x: 0, y: 176 },
    geometry: { exponent: 24 },
    base: {
      material: 'wireframe',
      paletteId: '15',
      line: 'dashed',
      lineColor: 'auto',
      effect: 'off',
    },
    stroke: { wire: 1.6, line: 2.2, face: 0, wireLine: 2.2 },
    // Hovering this bottom slab itself turns it into a solid metal "dstack" face (no inlay line).
    hover: (ctx: SquircleLayerHoverContext) => {
      if (ctx.hoveredLayerId === 'layer-1')
        return { material: 'solid', paletteId: '20', effect: 'metal', text: 'dstack', line: false }
      return false
    }
  },
  {
    id: 'layer-2',
    visible: true,
    offset: { x: 0, y: 88 },
    geometry: { exponent: 24 },
    base: {
      material: 'transparent',
      paletteId: '20',
      // line: false,
    },
    stroke: { face: 0 },
    // Cross-layer hover (0.1.4 resolver API): hovering the top (layer-3) or bottom (layer-1)
    // slab keeps this middle a wireframe; hovering the middle itself turns it transparent.
    hover: (ctx: SquircleLayerHoverContext) => {
      if (ctx.hoveredLayerId === 'layer-2') return { material: 'wireframe' };
      if (ctx.hoveredLayerId === 'layer-1')
        return { material: 'wireframe' };
      return false;
    },
  },
  {
    id: 'layer-3',
    visible: true,
    offset: { x: 0, y: 0 },
    geometry: { exponent: 24 },
    base: {
      material: 'solid',
      paletteId: '20',
      effect: 'metal',
      text: 'GPU',
      textColor: 'auto',
      textStyle: 'solid',
      // line: 'dotted',
      lineColor: 'auto',
      grain: true,
    },
    // Top "GPU" face hover behavior:
    //  - hovering itself (layer-3): becomes solid palette 20 with the metal effect;
    //  - hovering the bottom (layer-1): wireframe, "GPU" text outlined, inlay line removed;
    //  - hovering the middle (layer-2): wireframe, "GPU" text outlined (line kept).
    hover: (ctx: SquircleLayerHoverContext) => {
      if (ctx.hoveredLayerId === 'layer-1') return { material: 'wireframe', line: 'dotted', palletteId: 15, textStyle: 'wireframe' };
      // if (ctx.hoveredLayerId === 'layer-2') return { material: 'wireframe', line: 'dotted', palletteId: 15 };
      if (ctx.hoveredLayerId === 'layer-3') return { material: 'wireframe', line: 'dotted', palletteId: 15 };
      return false;
    },
  },
];

export function HeroSquircle({ theme }: { theme: ThemeMode }) {
  return (
    <div className="hero-squircle">
      <SquircleScene
        theme={theme}
        layers={HERO_LAYERS}
        geometry={HERO_GEOMETRY}
        ariaLabel="dstack orchestration stack"
        // Clicking any layer scrolls to the Get-started section (like the hero "Get started" CTA).
        onLayerClick={() =>
          document.getElementById('resources')?.scrollIntoView({ behavior: 'smooth' })
        }
      />
    </div>
  );
}
