import { KeyboardEvent, ReactNode, useEffect, useRef, useState } from 'react';
import CodeView from '@cloudscape-design/code-view/code-view';
import shHighlight from '@cloudscape-design/code-view/highlight/sh';
import Button from '@cloudscape-design/components/button';
import { mainButtonStyle } from '../../cloudscape-theme';
import { gpuOffers } from '../../data/gpus';
import { installMethods, maxInstallLines, padYamlToLines } from '../../data/snippets';
import { DOCS_URL, docsUrl } from '../../routes';

const GITHUB_API_URL = 'https://api.github.com/repos/dstackai/dstack';

// Compact star count: 1340 → "1.3k", 12000 → "12k", 980 → "980" (mirrors the Products menu).
function formatStars(count: number): string {
  if (count < 1000) return String(count);
  const thousands = count / 1000;
  return `${thousands >= 10 ? Math.round(thousands) : Number(thousands.toFixed(1))}k`;
}

// Product glyphs. GitHub mark doubles as the open-source star badge; cloud / box mark the
// hosted / self-hosted rows (thin-line, matching the Products menu).
const GithubGlyph = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
  </svg>
);
export const CloudGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
  </svg>
);
const BoxGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" /><path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" />
  </svg>
);
// Factory capability glyphs (thin-line, matching the Products menu). Distinct from the
// box product mark in the switcher — one icon per capability.
const KeyGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="7.5" cy="15.5" r="3.5" />
    <path d="m10 13 8-8M16 3l3 3-2 2-3-3" />
  </svg>
);
const ShieldGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3 5 6v5c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6l-7-3Z" />
    <path d="m9.5 12 1.8 1.8L15 10" />
  </svg>
);
const AuditGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="5" y="4" width="14" height="17" rx="2" />
    <path d="M9 4V3h6v1" />
    <path d="M9 10h6M9 14h6M9 18h3" />
  </svg>
);
// GPU chip glyph for the marketplace rows.
const ChipGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect width="16" height="16" x="4" y="4" rx="2" />
    <rect width="6" height="6" x="9" y="9" />
    <path d="M15 2v2" />
    <path d="M15 20v2" />
    <path d="M2 15h2" />
    <path d="M2 9h2" />
    <path d="M20 15h2" />
    <path d="M20 9h2" />
    <path d="M9 2v2" />
    <path d="M9 20v2" />
  </svg>
);
// On-prem glyphs (shared with the landing's "bring your own compute" block).
export const ServerGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect width="20" height="8" x="2" y="2" rx="2" />
    <rect width="20" height="8" x="2" y="14" rx="2" />
    <path d="M6 6h.01" />
    <path d="M6 18h.01" />
  </svg>
);
// The Kubernetes helm wheel from /static/logos/kubernetes.svg, inlined with currentColor so it
// takes the capability-icon color in both themes (the asset has hardcoded black fills).
export const KubernetesGlyph = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="m7.567 8.5945 0.4325 0.208 0.4315 -0.2075 0.107 -0.4655 -0.2985 -0.3735 -0.4805 0 -0.2995 0.3725 0.1075 0.466z" />
    <path d="m7.1083 6.94 0.0012 0.00095a0.26195 0.26195 0 0 0 0.41605 -0.20065l0 -0.0015 0.00635 -0.00315 0.0891 -1.57065c-0.10865 0.0134 -0.215 0.03175 -0.31665 0.0547a3.1 3.1 0 0 0 -1.48635 0.8088l1.2876 0.91285Z" />
    <path d="m6.41735 8.1311 0.0015 -0.0005a0.26205 0.26205 0 0 0 0.103 -0.4504l-0.0012 -0.001 0.00145 -0.00635 -1.17575 -1.05175a3.08875 3.08875 0 0 0 -0.4373 1.95l1.5071 -0.435Z" />
    <path d="M6.93225 9.2505a0.26145 0.26145 0 0 0 -0.30295 -0.19945l-0.0017 0 -0.00245 -0.00315 -1.5454 0.26245a3.1026 3.1026 0 0 0 1.24315 1.5554l0.5986 -1.44675 -0.00435 -0.00585 0.00045 -0.0015a0.2592 0.2592 0 0 0 0.01465 -0.16115Z" />
    <path d="m8.2311 9.82155 -0.00075 -0.00125a0.265 0.265 0 0 0 -0.24 -0.13795 0.26345 0.26345 0 0 0 -0.2217 0.13845l-0.00075 0.00145h-0.0014l-0.76 1.37405a3.11385 3.11385 0 0 0 1.69 0.08615c0.1035 -0.0234 0.205 -0.052 0.3022 -0.0842l-0.7617 -1.3767Z" />
    <path d="m9.36855 9.045 -0.0017 0a0.255 0.255 0 0 0 -0.0603 -0.0044 0.26315 0.26315 0 0 0 -0.2273 0.36595l0.0005 0.0012 -0.002 0.0027 0.605 1.4617A3.0925 3.0925 0 0 0 10.93 9.305l-1.5588 -0.26345Z" />
    <path d="m10.64465 6.62185 -1.16915 1.04635 0.0007 0.0032 -0.0012 0.00095a0.26245 0.26245 0 0 0 0.10275 0.4507l0.00175 0.00025 0.0012 0.0066 1.51465 0.436a3.14575 3.14575 0 0 0 -0.4507 -1.94405Z" />
    <path d="m8.46915 6.73365 0 0.00145a0.25805 0.25805 0 0 0 0.05715 0.15185 0.2618 0.2618 0 0 0 0.3596 0.04835l0.00125 -0.00095 0.0044 0.00195 1.2793 -0.907a3.11535 3.11535 0 0 0 -1.792 -0.86425l0.08885 1.56785Z" />
    <path d="m15.1903 9.5188 -1.2395 -5.38355a0.95285 0.95285 0 0 0 -0.519 -0.6455L8.415 1.09425a0.9666 0.9666 0 0 0 -0.8328 0L2.5663 3.49095a0.9536 0.9536 0 0 0 -0.51905 0.6455L0.8097 9.52a0.945 0.945 0 0 0 0.1303 0.7295 0.9182 0.9182 0 0 0 0.0544 0.0757l3.47195 4.3169a0.9622 0.9622 0 0 0 0.75 0.3579l5.56785 -0.0012a0.96255 0.96255 0 0 0 0.75 -0.35745l3.4708 -4.3174a0.94555 0.94555 0 0 0 0.1853 -0.80515Zm-1.90575 -0.065a0.3216 0.3216 0 0 1 -0.3906 0.22145l-0.00195 0 -0.00245 -0.0005 -0.00345 -0.00095 -0.0024 -0.001 -0.0286 -0.00585c-0.0173 -0.0034 -0.035 -0.0071 -0.04905 -0.01075a1.23215 1.23215 0 0 1 -0.17945 -0.0664c-0.0288 -0.01245 -0.0586 -0.02565 -0.09035 -0.0376l-0.00875 -0.00315a2.7596 2.7596 0 0 0 -0.5142 -0.15065 0.20595 0.20595 0 0 0 -0.1477 0.04905l-0.01855 0.0127 -0.00095 0.00075 -0.001 0c-0.02195 -0.0044 -0.0874 -0.0161 -0.12595 -0.0222a3.9083 3.9083 0 0 1 -1.7295 2.1755c0.00465 0.011 0.01 0.025 0.01535 0.0403a0.4676 0.4676 0 0 0 0.03345 0.07835l0.001 0.001 -0.0005 0.00145 -0.0083 0.021a0.2074 0.2074 0 0 0 -0.015 0.15455 2.845 2.845 0 0 0 0.2661 0.47585c0.0188 0.02805 0.03785 0.0542 0.0564 0.07955a1.2 1.2 0 0 1 0.10475 0.16c0.0083 0.0156 0.01855 0.0376 0.0276 0.05685l0.01145 0.0242a0.30415 0.30415 0 1 1 -0.54735 0.2588l-0.0112 -0.02275c-0.0093 -0.019 -0.01905 -0.0388 -0.0259 -0.0544a1.25295 1.25295 0 0 1 -0.06055 -0.1829c-0.0083 -0.02975 -0.01685 -0.06075 -0.02685 -0.0925l-0.00295 -0.0083a2.77205 2.77205 0 0 0 -0.2026 -0.4961 0.20885 0.20885 0 0 0 -0.13135 -0.08545l-0.02075 -0.00635 -0.00075 0 -0.00075 -0.00095c-0.005 -0.00855 -0.01685 -0.03055 -0.02975 -0.05375 -0.01175 -0.021 -0.0242 -0.0437 -0.0332 -0.06a3.9434 3.9434 0 0 1 -0.51345 0.15455 3.8794 3.8794 0 0 1 -2.255 -0.16165l-0.0676 0.1221 -0.001 0.0005a0.2405 0.2405 0 0 0 -0.12815 0.062 1.14135 1.14135 0 0 0 -0.168 0.36035c-0.02 0.0586 -0.04 0.11915 -0.06395 0.17845 -0.01025 0.032 -0.0188 0.0635 -0.02685 0.094a1.23735 1.23735 0 0 1 -0.06 0.18115c-0.00635 0.015 -0.01565 0.03345 -0.02465 0.05125l-0.01225 0.0247 -0.00025 0.0012 -0.00095 0.001a0.33865 0.33865 0 0 1 -0.2976 0.19725 0.2742 0.2742 0 0 1 -0.12 -0.0271 0.3213 0.3213 0 0 1 -0.1289 -0.43c0.0044 -0.00855 0.0088 -0.01855 0.0137 -0.0288 0.00855 -0.01855 0.0173 -0.03785 0.025 -0.05225a1.265 1.265 0 0 1 0.105 -0.1611c0.01835 -0.025 0.03735 -0.0513 0.0559 -0.0789a2.91045 2.91045 0 0 0 0.2715 -0.488 0.29445 0.29445 0 0 0 -0.0266 -0.168l0 -0.00095 0 -0.001 0.0537 -0.12865a3.9112 3.9112 0 0 1 -1.73 -2.16l-0.12965 0.0222 -0.00075 -0.0005 -0.0132 -0.00755a0.29805 0.29805 0 0 0 -0.15795 -0.053 2.77235 2.77235 0 0 0 -0.51415 0.15065l-0.00855 0.0032c-0.031 0.01195 -0.06055 0.0244 -0.0891 0.0366a1.24745 1.24745 0 0 1 -0.18065 0.06665c-0.0154 0.00415 -0.0354 0.00855 -0.0547 0.01245l-0.02295 0.005 -0.00245 0.00095 -0.0034 0.001 -0.00245 0.0005 -0.00195 0a0.3039 0.3039 0 1 1 -0.13475 -0.59l0.00195 -0.0005 0.00265 -0.00075 0.001 0 0.0017 -0.00045 0.02345 -0.00565c0.02 -0.005 0.0405 -0.01 0.05665 -0.0129a1.2066 1.2066 0 0 1 0.1904 -0.01785c0.0315 -0.0012 0.0642 -0.0027 0.0979 -0.00535l0.0071 -0.00075A2.777 2.777 0 0 0 3.885 8.96a0.36 0.36 0 0 0 0.1155 -0.1135l0.0122 -0.0159 0.0005 -0.0007 0.0007 0 0.12355 -0.0359a3.88825 3.88825 0 0 1 0.6123 -2.7063l-0.095 -0.085 0 -0.001 -0.0022 -0.0139a0.29915 0.29915 0 0 0 -0.05765 -0.15795 2.80855 2.80855 0 0 0 -0.4458 -0.31325c-0.02925 -0.0171 -0.05785 -0.03245 -0.08565 -0.0471a1.23655 1.23655 0 0 1 -0.16335 -0.09865c-0.0132 -0.00975 -0.0293 -0.02295 -0.0447 -0.03565l-0.0178 -0.0144 -0.0026 -0.00145 -0.00245 -0.00195a0.35225 0.35225 0 0 1 -0.1305 -0.2174 0.28625 0.28625 0 0 1 0.0564 -0.22875A0.29175 0.29175 0 0 1 4 4.7644a0.3613 0.3613 0 0 1 0.2107 0.0796l0.01805 0.01415c0.0166 0.01295 0.035 0.0276 0.0486 0.03905a1.2627 1.2627 0 0 1 0.13355 0.13795c0.02 0.02345 0.04125 0.0476 0.0642 0.07205l0.005 0.005a2.76105 2.76105 0 0 0 0.39945 0.36 0.20795 0.20795 0 0 0 0.155 0.0203l0.0215 -0.00345h0.00095l0.00075 0.0005c0.01785 0.0132 0.0742 0.0537 0.1067 0.0757a3.86365 3.86365 0 0 1 1.96165 -1.12 3.98355 3.98355 0 0 1 0.5408 -0.08325l0.00705 -0.12575 0.0005 -0.0007a0.3243 0.3243 0 0 0 0.09695 -0.1538 2.78895 2.78895 0 0 0 -0.033 -0.53955l-0.00045 -0.0044c-0.00465 -0.0332 -0.0105 -0.065 -0.0164 -0.0957a1.28055 1.28055 0 0 1 -0.02465 -0.19c-0.00045 -0.015 -0.00025 -0.03395 0 -0.05225l0.00025 -0.025 -0.00025 -0.00365 0 -0.00465a0.3044 0.3044 0 1 1 0.6055 0l0.00045 0.03025c0.0005 0.0193 0.00075 0.03955 0.00025 0.055a1.2674 1.2674 0 0 1 -0.02465 0.19c-0.00585 0.03075 -0.0117 0.0625 -0.01635 0.0957l-0.00195 0.01585a2.72395 2.72395 0 0 0 -0.032 0.52835 0.2066 0.2066 0 0 0 0.0808 0.1333l0.0164 0.015 0.00095 0.00075v0.00095c0.00075 0.02175 0.00415 0.0918 0.00685 0.13185a3.895 3.895 0 0 1 1.35865 0.37795 3.9406 3.9406 0 0 1 1.1316 0.825l0.113 -0.0806h0.001l0.0156 0.001a0.2957 0.2957 0 0 0 0.165 -0.0205 2.74425 2.74425 0 0 0 0.39355 -0.355l0.01075 -0.011c0.0227 -0.0239 0.04345 -0.0476 0.0637 -0.0708a1.285 1.285 0 0 1 0.135 -0.13915c0.01315 -0.01145 0.031 -0.025 0.04835 -0.0388l0.0183 -0.0144a0.3044 0.3044 0 1 1 0.3772 0.4736l-0.02175 0.01785c-0.01535 0.0127 -0.0315 0.02585 -0.0442 0.0354a1.23665 1.23665 0 0 1 -0.1633 0.0984c-0.0281 0.01465 -0.05715 0.03 -0.0867 0.04735a2.84445 2.84445 0 0 0 -0.44605 0.31345 0.2076 0.2076 0 0 0 -0.05395 0.1465l-0.0017 0.022v0.00095l-0.0007 0.0005c-0.0081 0.0073 -0.0254 0.02295 -0.0457 0.041s-0.0432 0.0386 -0.0593 0.05325a3.89915 3.89915 0 0 1 0.625 2.6997l0.12 0.035 0.0005 0.0005 0.00855 0.0127a0.3007 0.3007 0 0 0 0.12 0.1167 2.7975 2.7975 0 0 0 0.5315 0.08785l0.0061 0.0005c0.0337 0.00295 0.0664 0.00415 0.09815 0.0054a1.23085 1.23085 0 0 1 0.19 0.0178c0.0156 0.00295 0.03565 0.0078 0.055 0.0127l0.0322 0.0078a0.3215 0.3215 0 0 1 0.25605 0.3697Z" />
  </svg>
);

// Read-only shell snippet. Line wrapping is left off so padded snippets stay
// equal height across tabs (see padYamlToLines).
function ShellCode({ content }: { content: string }) {
  return (
    <div className="code-snippet">
      <CodeView ariaLabel="Installation commands" content={content} highlight={shHighlight} />
    </div>
  );
}

type DeployTab = 'oss' | 'sky' | 'factory';


const UserGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);
const ShareGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="18" cy="5" r="3" />
    <circle cx="6" cy="12" r="3" />
    <circle cx="18" cy="19" r="3" />
    <path d="m8.59 13.51 6.83 3.98" />
    <path d="m15.41 6.51-6.82 3.98" />
  </svg>
);
// Remaining Factory glyphs, same thin-line style as the capability icons.
const GaugeGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m12 14 4-4" />
    <path d="M3.34 19a10 10 0 1 1 17.32 0" />
  </svg>
);
const LayersGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z" />
    <path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65" />
    <path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65" />
  </svg>
);

// dstack Factory tab contents: icon + title + subtitle rows per tab. Only Factory-exclusive
// capabilities live here — bringing clouds/on-prem is core dstack and is shown in the Explore
// section's "bring your own compute" block instead.
// Rendered with column flow (see .gs-caps--cols): the first three fill the left column, the
// rest the right — and the mobile single column keeps this same order.
const FACTORY_GOVERNANCE = [
  { icon: <UserGlyph />, title: 'Single Sign-On (SSO)', sub: 'Okta, Microsoft Entra, Google Workspace' },
  { icon: <AuditGlyph />, title: 'Audit logs', sub: 'Track system events across tenants (projects and users)' },
  { icon: <KeyGlyph />, title: 'Fine-grained tokens', sub: 'Multiple user tokens with fine-grained permissions' },
  { icon: <ShareGlyph />, title: 'Sharable resources', sub: 'Share fleets and gateways across tenants (projects)' },
  { icon: <GaugeGlyph />, title: 'Compute metering', sub: 'Usage metering and quotas per tenant (project or user)' },
  { icon: <ShieldGlyph />, title: 'Air-gapped deployment', sub: 'Runs in isolated environments with no Internet access' },
];
// The preset registry: private (your own) in dstack Factory, public in dstack Sky.
const FACTORY_PRESETS = [
  { icon: <LayersGlyph />, title: 'Private registry', sub: 'Sharing optimized inference serving configurations' },
  { icon: <GaugeGlyph />, title: 'Token metering', sub: 'Token metering and quotas per tenant (project or user)' },
];
const SKY_PRESETS = [
  { icon: <LayersGlyph />, title: 'Public registry', sub: 'Sharing optimized inference serving configurations' },
];

// Icon + title + subtitle rows, shared by the Factory tabs and the explore block.
export function CapList({ items, columnFlow }: { items: { icon: ReactNode; title: string; sub: string }[]; columnFlow?: boolean }) {
  return (
    <ul className={`gs-caps${columnFlow ? ' gs-caps--cols' : ''}`}>
      {items.map(cap => (
        <li key={cap.title} className="gs-cap">
          <span className="gs-cap__ic">{cap.icon}</span>
          <span className="gs-cap__b">
            <span className="gs-cap__t">{cap.title}</span>
            <span className="gs-cap__s">{cap.sub}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

// Closing "Get started" section: the product switcher rail (also rendered by the Products menu
// and the docs header popup) beside each product's detail box. Open-source shows the install
// code, Factory shows governance and its private preset registry, Sky the GPU marketplace and
// the public preset registry.
// NOTE: the three product descriptions below are duplicated in SiteNavigation.tsx (products)
// and mkdocs/overrides/header-2.html — keep all three in sync.
export function GetStartedSection() {
  const [tab, setTab] = useState<DeployTab>('oss');
  // The selection indicator: one white card that slides to the selected row.
  const railRef = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState<{ top: number; height: number } | null>(null);
  const [method, setMethod] = useState<(typeof installMethods)[number]['id']>(installMethods[0].id);
  // dstack Sky and Factory panes: which of their tabs is shown (same interaction as the
  // install-method tabs).
  const [skyPane, setSkyPane] = useState<'marketplace' | 'presets'>('marketplace');
  const [factoryPane, setFactoryPane] = useState<'governance' | 'registry'>('governance');
  const [stars, setStars] = useState<number | null>(null);

  // Live star count for the open-source tile, fetched once. Best-effort: if the API is rate-limited
  // or errors, the badge simply doesn't render.
  useEffect(() => {
    let active = true;
    fetch(GITHUB_API_URL)
      .then(response => (response.ok ? response.json() : null))
      .then(data => {
        if (active && data && typeof data.stargazers_count === 'number') setStars(data.stargazers_count);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  // Each option behaves like a tab: click or Enter/Space selects it.
  const optionProps = (id: DeployTab) => ({
    role: 'tab',
    'aria-selected': tab === id,
    tabIndex: 0,
    onClick: () => setTab(id),
    onMouseEnter: () => setTab(id),
    onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        setTab(id);
      }
    },
  });

  const activeInstall = installMethods.find(m => m.id === method) ?? installMethods[0];

  // Keep the indicator glued to the selected row (on selection change, resize, and once the star
  // count loads — it grows the first row). Fractional rect math, not offsetTop/offsetHeight: those
  // round to integers while the layout is fractional, leaving up-to-1px slivers at the row edges.
  useEffect(() => {
    const update = () => {
      const rail = railRef.current;
      const selected = rail?.querySelector<HTMLElement>('.gs-opt--on');
      if (!rail || !selected) return;
      const railBox = rail.getBoundingClientRect();
      const rowBox = selected.getBoundingClientRect();
      const borderTop = parseFloat(getComputedStyle(rail).borderTopWidth) || 0;
      setIndicator({ top: rowBox.top - railBox.top - borderTop, height: rowBox.height });
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [tab, stars]);

  return (
    <section className="docs-section" id="resources">
      <h2>Get started</h2>

      <div className="gs-deploy">
        {/* Left: the popup-style selector. */}
        <div className="gs-rail" role="tablist" aria-label="Deployment" ref={railRef}>
          {indicator && <div className="gs-rail__indicator" style={{ top: indicator.top, height: indicator.height }} aria-hidden="true" />}
          <div className="gs-rail__group">Self-hosted</div>
          <div className={`gs-opt gs-opt--feat${tab === 'oss' ? ' gs-opt--on' : ''}`} {...optionProps('oss')}>
            <span className="gs-opt__icwrap">
              <span className="gs-opt__ic"><GithubGlyph /></span>
              {stars !== null && (
                <span className="gs-opt__stars" aria-label={`${stars} GitHub stars`}>{formatStars(stars)}</span>
              )}
            </span>
            <span className="gs-opt__body">
              <span className="gs-opt__name">dstack</span>
              <span className="gs-opt__desc">The open-source control plane for AI-native orchestration.</span>
            </span>
          </div>

          <div className={`gs-opt gs-opt--row${tab === 'factory' ? ' gs-opt--on' : ''}`} {...optionProps('factory')}>
            <span className="gs-opt__ic"><BoxGlyph /></span>
            <span className="gs-opt__body">
              <span className="gs-opt__name">dstack Factory</span>
              <span className="gs-opt__desc">Extends dstack with a governance and metering layer, and a private preset registry.</span>
            </span>
          </div>

          <div className="gs-rail__group">Hosted by us</div>
          <div className={`gs-opt gs-opt--row${tab === 'sky' ? ' gs-opt--on' : ''}`} {...optionProps('sky')}>
            <span className="gs-opt__ic"><CloudGlyph /></span>
            <span className="gs-opt__body">
              <span className="gs-opt__name">dstack Sky</span>
              <span className="gs-opt__desc">Everything in dstack Factory, plus the GPU marketplace and the public preset registry.</span>
            </span>
          </div>
        </div>

        {/* Open-source: install-method tabs + read-only code + footer CTA bar. */}
        {tab === 'oss' && (
          <div className="gs-detail" key="oss">
            <div className="gs-box">
              <div className="gs-tabs" role="tablist" aria-label="Install method">
                {installMethods.map(m => (
                  <button
                    key={m.id}
                    type="button"
                    role="tab"
                    aria-selected={m.id === method}
                    className={`gs-tab${m.id === method ? ' gs-tab--on' : ''}`}
                    onClick={() => setMethod(m.id)}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
              <div className="gs-codebody">
                <ShellCode content={padYamlToLines(activeInstall.code, maxInstallLines)} />
              </div>
              <div className="gs-boxfoot">
                <Button variant="primary" href={docsUrl('installation')} style={mainButtonStyle}>Install open-source</Button>
                <Button href={DOCS_URL} style={mainButtonStyle}>View docs</Button>
              </div>
            </div>
          </div>
        )}

        {/* dstack Sky: GPU marketplace + the public preset registry; footer CTA. */}
        {tab === 'sky' && (
          <div className="gs-detail" key="sky">
            <div className="gs-box">
              {/* Real tabs, like the open-source box's uv/pip/Docker — one pane shown at a time. */}
              <div className="gs-tabs" role="tablist" aria-label="dstack Sky">
                <button
                  type="button"
                  role="tab"
                  aria-selected={skyPane === 'marketplace'}
                  className={`gs-tab${skyPane === 'marketplace' ? ' gs-tab--on' : ''}`}
                  onClick={() => setSkyPane('marketplace')}
                >
                  GPU marketplace
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={skyPane === 'presets'}
                  className={`gs-tab${skyPane === 'presets' ? ' gs-tab--on' : ''}`}
                  onClick={() => setSkyPane('presets')}
                >
                  AI token factory
                </button>
              </div>
              <div className="gs-skybody">
                {skyPane === 'marketplace' && (
                  <ul className="gs-col__list gs-col__list--grid gs-col__list--offers">
                    {gpuOffers.map(gpu => (
                      <li key={`${gpu.name} ${gpu.memory}`} className="gs-mkt__row">
                        <span className="gs-mkt__left">
                          <span className="gs-li__ic"><ChipGlyph /></span>
                          <span className="gs-mkt__g"><span className="gs-mkt__name">{gpu.name}</span>{' '}{gpu.memory}</span>
                        </span>
                        <span className="gs-mkt__p">{gpu.price}/hr</span>
                      </li>
                    ))}
                  </ul>
                )}
                {skyPane === 'presets' && <CapList items={SKY_PRESETS} />}
              </div>
              <div className="gs-boxfoot">
                {skyPane === 'marketplace' && (
                  <span className="gs-foot__note">
                    <span className="gs-foot__full">Access compute from a pool of providers. Sign up to get $5 credit.</span>
                    <span className="gs-foot__short">Sign up to get $5 credit</span>
                  </span>
                )}
                {skyPane === 'presets' && (
                  <span className="gs-foot__note">Pull ready-to-deploy presets from the public registry</span>
                )}
                <Button variant="primary" href="https://sky.dstack.ai" target="_blank" iconName="external" iconAlign="right" style={mainButtonStyle}>Sign up</Button>
                <Button href="https://sky.dstack.ai" target="_blank" iconName="external" iconAlign="right" style={mainButtonStyle}>Sign in</Button>
              </div>
            </div>
          </div>
        )}

        {/* dstack Factory: only the Factory-exclusive capabilities — governance first, then the
            private preset registry. */}
        {tab === 'factory' && (
          <div className="gs-detail" key="factory">
            <div className="gs-box">
              <div className="gs-tabs" role="tablist" aria-label="dstack Factory">
                <button
                  type="button"
                  role="tab"
                  aria-selected={factoryPane === 'governance'}
                  className={`gs-tab${factoryPane === 'governance' ? ' gs-tab--on' : ''}`}
                  onClick={() => setFactoryPane('governance')}
                >
                  Governance
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={factoryPane === 'registry'}
                  className={`gs-tab${factoryPane === 'registry' ? ' gs-tab--on' : ''}`}
                  onClick={() => setFactoryPane('registry')}
                >
                  AI token factory
                </button>
              </div>
              <div className="gs-skybody">
                {factoryPane === 'governance' && <CapList items={FACTORY_GOVERNANCE} columnFlow />}
                {factoryPane === 'registry' && <CapList items={FACTORY_PRESETS} />}
              </div>
              <div className="gs-boxfoot">
                {factoryPane === 'registry' && (
                  <span className="gs-foot__note">Push and pull presets within your organization</span>
                )}
                <Button variant="primary" href="https://calendly.com/dstackai/discovery-call" target="_blank" iconName="external" iconAlign="right" style={mainButtonStyle}>Book a demo</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
