import { asset } from '../asset';

// Layered "vendor-agnostic" architecture diagram, rebuilt as HTML/CSS (replaces the previous
// static SVG). Logos are recolored to the current text color via CSS masking (see .arch-logo in
// styles.css) so they read monochrome and flip with the light/dark theme. Per-logo size/aspect
// lives in CSS (.arch-logo--<key>); only the mask image URL is set inline, since it must carry
// the runtime base path (asset()).
//
// NOTE: This component is the SOURCE for the static SVG pair published in
// https://github.com/dstackai/static-assets (static-assets/images/dstack-architecture-diagram*.svg,
// served via https://dstack.ai/static-assets/static-assets/images/) and embedded by the docs
// index ("How does it work?") and the README. If you change this component (markup, logos, or
// sizing), regenerate the SVGs from it and overwrite them in place — the URLs stay stable.

type Logo = { key: string; label: string; src?: string; initials?: string };

const logoSrc = (file: string) => asset(`/static/logos/${file}`);

const FRAMEWORKS: Logo[] = [
  { key: 'pytorch', label: 'PyTorch', src: logoSrc('pytorch.svg') },
  { key: 'vllm', label: 'vLLM', src: logoSrc('vllm.svg') },
  { key: 'sglang', label: 'SGLang', src: logoSrc('sglang.svg') },
  { key: 'smg', label: 'SMG', src: logoSrc('smg.svg') },
];

const MODELS: Logo[] = [
  { key: 'glm', label: 'GLM', src: logoSrc('glm.svg') },
  { key: 'deepseek', label: 'DeepSeek', src: logoSrc('deepseek.svg') },
  { key: 'qwen', label: 'Qwen', src: logoSrc('qwen.svg') },
  { key: 'kimi', label: 'Kimi', src: logoSrc('kimi.svg') },
];

const DOCKER: Logo = { key: 'docker', label: 'Docker', src: logoSrc('docker.svg') };

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
      <div className="arch-diagram" role="img" aria-label="dstack architecture: an orchestration layer between AI frameworks and models on top, and GPU clouds, Kubernetes, VMs, bare-metal, and hardware below.">
        {/* Top: what plugs in on top of the orchestration layer. */}
        <div className="arch-row arch-row--inputs">
          <div className="arch-cell">
            <span className="arch-cell__label">Any framework</span>
            <LogoRow logos={FRAMEWORKS} />
          </div>
          <div className="arch-cell arch-cell--model">
            <span className="arch-cell__label">Any model</span>
            <LogoRow logos={MODELS} />
          </div>
        </div>

        {/* Middle: the orchestration layer itself */}
        <div className="arch-orchestration">
          <div className="arch-orchestration__title">
            <span>dstack orchestration</span>
            <LogoMark logo={DOCKER} />
          </div>
          <div className="arch-orchestration__cells">
            {['Projects', 'Fleets', 'Runs', 'Presets', 'Gateways'].map(name => (
              <div className="arch-subcell" key={name}>
                {name}
              </div>
            ))}
          </div>
        </div>

        {/* Bottom: where workloads run */}
        <div className="arch-row arch-row--compute">
          <div className="arch-cell arch-cell--gpu">
            <LogoRow logos={GPU_CLOUDS} />
            <span className="arch-cell__label">Clouds</span>
          </div>
          <div className="arch-cell arch-cell--platform">
            <LogoMark logo={KUBERNETES} />
            <span className="arch-cell__label">Kubernetes</span>
          </div>
          <div className="arch-cell arch-cell--platform">
            <span className="arch-cell__label">VMs or bare-metal</span>
          </div>
        </div>

        <div className="arch-cell arch-cell--full arch-cell--hw">
          <span className="arch-cell__label">Any hardware</span>
          <LogoRow logos={HARDWARE} />
        </div>
      </div>
    </div>
  );
}
