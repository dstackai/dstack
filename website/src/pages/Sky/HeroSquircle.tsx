import {
  SquircleScene,
  type SquircleGeometryConfig,
  type SquircleLayerConfig,
  type SquircleLayerHoverContext,
} from '@dstackai/sqircle';
import '@dstackai/sqircle/style.css';
import type { ThemeMode } from '../../theme';

const HERO_GEOMETRY: SquircleGeometryConfig = {
  angleDegrees: 20,
};

// Default and bottom-layer hover are reversed from the main homepage.
const HERO_LAYERS: SquircleLayerConfig[] = [
  {
    id: 'layer-1',
    visible: true,
    offset: { x: 0, y: 176 },
    base: {
      material: 'solid',
      paletteId: '13',
      line: false,
      effect: 'metal',
      text: 'dstack',
      grain: true,
    },
    stroke: { wire: 1.6, line: 2.2, face: 0, wireLine: 2.2 },
    hover: () => ({
      material: 'wireframe',
      paletteId: '15',
      line: 'dashed',
      effect: 'off',
      text: false,
    }),
  },
  {
    id: 'layer-2',
    visible: true,
    offset: { x: 0, y: 88 },
    base: {
      material: 'wireframe',
      paletteId: '15',
      line: 'dotted',
    },
    stroke: { face: 0 },
    hover: (ctx: SquircleLayerHoverContext) => {
      if (ctx.hoveredLayerId === 'layer-2') return false;
      return { material: 'transparent' };
    },
  },
  {
    id: 'layer-3',
    visible: true,
    offset: { x: 0, y: 0 },
    base: {
      material: 'wireframe',
      paletteId: '15',
      effect: 'metal',
      text: 'GPU',
      textColor: 'auto',
      lineColor: 'auto',
      grain: true,
    },
    hover: (ctx: SquircleLayerHoverContext) => {
      if (ctx.hoveredLayerId === 'layer-3') return { textStyle: 'solid' };
      return { material: 'solid', textStyle: 'solid', line: false };
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
        ariaLabel="dstack Sky"
        onLayerClick={() =>
          document.getElementById('compute')?.scrollIntoView({ behavior: 'smooth' })
        }
      />
    </div>
  );
}
