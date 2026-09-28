import { useMemo } from 'react';
import {
  SquircleScene,
  type SquircleGeometryConfig,
  type SquircleLayerConfig,
  type SquircleLayerHoverContext,
  type SquirclePaletteId,
} from '@dstackai/sqircle';
import '@dstackai/sqircle/style.css';
import type { ThemeMode } from '../theme';

// Home-style layers, back to front: dashed wireframe, transparent, and solid metal.
// Factory uses the same materials and hover behavior with a different label and palette.
const HERO_GEOMETRY: SquircleGeometryConfig = {
  angleDegrees: 20,
};

const createHeroLayers = (topLabel: string, paletteId: SquirclePaletteId): SquircleLayerConfig[] => [
  {
    id: 'layer-1',
    visible: true,
    offset: { x: 0, y: 176 },
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
        return { material: 'solid', paletteId, effect: 'metal', text: 'dstack', line: false };
      return false;
    },
  },
  {
    id: 'layer-2',
    visible: true,
    offset: { x: 0, y: 88 },
    base: {
      material: 'transparent',
      paletteId,
    },
    stroke: { face: 0 },
    hover: (ctx: SquircleLayerHoverContext) => {
      if (ctx.hoveredLayerId === 'layer-2') return { material: 'wireframe' };
      if (ctx.hoveredLayerId === 'layer-1') return { material: 'wireframe' };
      return false;
    },
  },
  {
    id: 'layer-3',
    visible: true,
    offset: { x: 0, y: 0 },
    base: {
      material: 'solid',
      paletteId,
      effect: 'metal',
      text: topLabel,
      textColor: 'auto',
      textStyle: 'solid',
      lineColor: 'auto',
      grain: true,
    },
    hover: (ctx: SquircleLayerHoverContext) => {
      if (ctx.hoveredLayerId === 'layer-1') return { material: 'wireframe', line: 'dotted', textStyle: 'wireframe' };
      if (ctx.hoveredLayerId === 'layer-3') return { material: 'wireframe', line: 'dotted' };
      return false;
    },
  },
];

export function HeroSquircle({
  theme,
  topLabel = 'GPU',
  paletteId = '20',
  ariaLabel = 'dstack orchestration stack',
}: {
  theme: ThemeMode;
  topLabel?: string;
  paletteId?: SquirclePaletteId;
  ariaLabel?: string;
}) {
  const layers = useMemo(() => createHeroLayers(topLabel, paletteId), [topLabel, paletteId]);

  return (
    <div className="hero-squircle">
      <SquircleScene
        theme={theme}
        layers={layers}
        geometry={HERO_GEOMETRY}
        ariaLabel={ariaLabel}
        // Clicking any layer scrolls to the Get-started section (like the hero "Get started" CTA).
        onLayerClick={() =>
          document.getElementById('resources')?.scrollIntoView({ behavior: 'smooth' })
        }
      />
    </div>
  );
}
