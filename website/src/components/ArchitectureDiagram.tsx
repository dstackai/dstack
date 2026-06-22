import { asset } from '../asset';
import { DashedBorder } from './DashedBorder';

// Layered "vendor-agnostic" architecture diagram, rebuilt as HTML/CSS (replaces the previous
// static SVG). Logos are recolored to the current text color via CSS masking (see .arch-logo in
// styles.css) so they read monochrome and flip with the light/dark theme. Per-logo size/aspect
// lives in CSS (.arch-logo--<key>); only the mask image URL is set inline, since it must carry
// the runtime base path (asset()).
//
// NOTE: This diagram is mirrored in the docs: mkdocs/docs/index.md ("How does it work?") embeds the
// same markup, with the styles ported to mkdocs/assets/stylesheets/cloudscape-docs.css (.arch-*)
// and the logos copied to mkdocs/assets/images/arch-logos/. If you change this component (markup,
// logos, or sizing), update the docs copy too so the two stay in sync.

type Logo = { key: string; label: string; src?: string; initials?: string };

const logoSrc = (file: string) => asset(`/static/logos/${file}`);

const FRAMEWORKS: Logo[] = [
  { key: 'pytorch', label: 'PyTorch', src: logoSrc('pytorch.svg') },
  { key: 'vllm', label: 'vLLM', src: logoSrc('vllm.svg') },
  { key: 'sglang', label: 'SGLang', src: logoSrc('sglang.svg') },
  { key: 'meta', label: 'Meta', src: logoSrc('meta.svg') },
  { key: 'huggingface', label: 'Hugging Face', src: logoSrc('huggingface.svg') },
];

const GPU_CLOUDS: Logo[] = [
  { key: 'aws', label: 'AWS', src: logoSrc('aws.svg') },
  { key: 'gcp', label: 'Google Cloud', src: logoSrc('gcp.svg') },
  { key: 'lambda', label: 'Lambda', src: logoSrc('lambda.svg') },
  { key: 'nebius', label: 'Nebius', src: logoSrc('nebius.svg') },
  { key: 'runpod', label: 'RunPod', src: logoSrc('runpod.svg') },
];

const KUBERNETES: Logo = { key: 'kubernetes', label: 'Kubernetes', src: logoSrc('kubernetes.svg') };

const HARDWARE: Logo[] = [
  { key: 'nvidia', label: 'NVIDIA', src: logoSrc('nvidia.svg') },
  { key: 'amd', label: 'AMD', src: logoSrc('amd.webp') },
  { key: 'tenstorrent', label: 'Tenstorrent', src: logoSrc('tenstorrent.svg') },
  { key: 'tpu', label: 'Google TPU', src: logoSrc('gcp.svg') }, // TPU shares the GCP mark
];

function LogoMark({ logo }: { logo: Logo }) {
  if (logo.src) {
    return (
      <span
        className={`arch-logo arch-logo--${logo.key}`}
        role="img"
        aria-label={logo.label}
        style={{ WebkitMaskImage: `url(${logo.src})`, maskImage: `url(${logo.src})` }}
      />
    );
  }
  return (
    <span className={`arch-logo arch-logo--placeholder arch-logo--${logo.key}`} role="img" aria-label={logo.label}>
      {logo.initials}
    </span>
  );
}

function LogoRow({ logos }: { logos: Logo[] }) {
  return (
    <span className="arch-logos">
      {logos.map(logo => (
        <LogoMark key={logo.key} logo={logo} />
      ))}
    </span>
  );
}

export function ArchitectureDiagram() {
  return (
    <div className="arch-diagram-wrap">
      <div className="arch-diagram" role="img" aria-label="dstack architecture: an orchestration layer between AI frameworks, data, and models on top, and GPU clouds, Kubernetes, on-prem clusters, and hardware below.">
        {/* Top: what plugs in on top of the orchestration layer */}
        <div className="arch-row">
          <div className="arch-cell">
            <DashedBorder />
            <span className="arch-cell__label">Any framework</span>
            <LogoRow logos={FRAMEWORKS} />
          </div>
          <div className="arch-cell arch-cell--center">
            <DashedBorder />
            <span className="arch-cell__label">Your data</span>
          </div>
          <div className="arch-cell arch-cell--center">
            <DashedBorder />
            <span className="arch-cell__label">Any models</span>
          </div>
        </div>

        {/* Middle: the orchestration layer itself */}
        <div className="arch-orchestration">
          <div className="arch-orchestration__title">The AI-native orchestration stack</div>
          <div className="arch-orchestration__cells">
            {['Fleets', 'Dev environments', 'Tasks', 'Services', 'Volumes'].map(name => (
              <div className="arch-subcell" key={name}>
                <DashedBorder />
                {name}
              </div>
            ))}
          </div>
        </div>

        {/* Bottom: where workloads run */}
        <div className="arch-row">
          <div className="arch-cell arch-cell--gpu">
            <DashedBorder />
            <LogoRow logos={GPU_CLOUDS} />
            <span className="arch-cell__label">Any cloud</span>
          </div>
          <div className="arch-cell">
            <DashedBorder />
            <LogoRow logos={[KUBERNETES]} />
            <span className="arch-cell__label">Kubernetes</span>
          </div>
          <div className="arch-cell arch-cell--center">
            <DashedBorder />
            <span className="arch-cell__label">On-prem clusters</span>
          </div>
        </div>

        <div className="arch-cell arch-cell--full arch-cell--hw">
          <DashedBorder />
          <span className="arch-cell__label">Any hardware</span>
          <LogoRow logos={HARDWARE} />
        </div>
      </div>
    </div>
  );
}
