import { KeyboardEvent, useEffect, useState } from 'react';
import CodeView from '@cloudscape-design/code-view/code-view';
import shHighlight from '@cloudscape-design/code-view/highlight/sh';
import Button from '@cloudscape-design/components/button';
import { mainButtonStyle } from '../../cloudscape-theme';
import { gpuOffers } from '../../data/gpus';
import { installMethods, maxInstallLines, padYamlToLines } from '../../data/snippets';
import { docsUrl } from '../../routes';

const GITHUB_API_URL = 'https://api.github.com/repos/dstackai/dstack';

// Compact star count: 1340 → "1.3k", 12000 → "12k", 980 → "980" (mirrors the Products menu).
function formatStars(count: number): string {
  if (count < 1000) return String(count);
  const thousands = count / 1000;
  return `${thousands >= 10 ? Math.round(thousands) : Number(thousands.toFixed(1))}k`;
}

// Product glyphs. GitHub mark doubles as the open-source star badge; cloud / fingerprint mark the
// hosted / self-hosted rows (thin-line, matching the Products menu).
const GithubGlyph = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
  </svg>
);
const CloudUploadGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 14.899A6 6 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 .5 8.973" />
    <path d="M12 12v8" />
    <path d="m8 16 4-4 4 4" />
  </svg>
);
const FingerprintGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 10a2 2 0 0 0-2 2c0 1.5.4 3 1 4.3" />
    <path d="M12 6.5A5.5 5.5 0 0 0 6.5 12c0 2 .4 3.5 1.1 5" />
    <path d="M12 14v3.5" />
    <path d="M15.6 8.4A5.5 5.5 0 0 1 17.5 12c0 2.2-.5 4.3-1.3 6" />
    <path d="M12 3a9 9 0 0 0-9 9" />
    <path d="M21 12a9 9 0 0 0-3-6.7" />
  </svg>
);
const CheckGlyph = () => (
  <svg className="gs-check__mark" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m2.5 8.5 3.2 3.2L13.5 4" />
  </svg>
);
// Enterprise capability glyphs (thin-line, matching the Products menu). Distinct from the
// fingerprint product mark in the switcher — one icon per capability.
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
const SupportGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="12" r="3.5" />
    <path d="m6 6 3.5 3.5M18 6l-3.5 3.5M6 18l3.5-3.5M18 18l-3.5-3.5" />
  </svg>
);
const AuditGlyph = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="5" y="4" width="14" height="17" rx="2" />
    <path d="M9 4V3h6v1" />
    <path d="M9 10h6M9 14h6M9 18h3" />
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

type DeployTab = 'oss' | 'sky' | 'ent';

// dstack Sky: a sample of the GPU marketplace (price ranges, no provider/region — the point is
// "on-demand GPUs at a price"; same offers as the "Access marketplace GPUs" block) and the clouds
// you can bring instead. Both lists scroll.
const SKY_CLOUDS = ['AWS', 'GCP', 'Azure', 'Kubernetes', 'Lambda', 'RunPod', 'Nebius', 'OCI', 'Vast.ai', 'CloudRift', 'Crusoe', 'SSH fleets'];

// Enterprise "Extra" capabilities (beyond open-source). One tab for now; more can be added later.
const ENT_CAPS = [
  { icon: <KeyGlyph />, title: 'Single Sign-On (SSO)', sub: 'Okta, Microsoft Entra, Google Workspace' },
  { icon: <ShieldGlyph />, title: 'Air-gapped deployment', sub: 'Run fully offline, in your own VPC' },
  { icon: <SupportGlyph />, title: 'Dedicated support', sub: 'Bug fixes, feature prioritization, SLAs' },
  { icon: <AuditGlyph />, title: 'Audit logs & RBAC', sub: 'Fine-grained roles and audit trails' },
];

// Closing "Get started" section. The Products-popup component is reused as a vertical switcher
// (open-source featured + selected by default; dstack Sky / Enterprise as rows). Each tab's detail
// is a bordered box with a footer-bar CTA: open-source shows the install code, Sky shows the GPU
// marketplace alongside the clouds you can bring, Enterprise is a placeholder for now.
export function GetStartedSection() {
  const [tab, setTab] = useState<DeployTab>('oss');
  const [method, setMethod] = useState<(typeof installMethods)[number]['id']>(installMethods[0].id);
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
    onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        setTab(id);
      }
    },
  });

  const activeInstall = installMethods.find(m => m.id === method) ?? installMethods[0];

  return (
    <section className="docs-section" id="resources">
      <h2>Get started</h2>

      <div className="gs-deploy">
        {/* Left: the popup-style selector. */}
        <div className="gs-rail" role="tablist" aria-label="Deployment">
          <div className={`gs-opt gs-opt--feat${tab === 'oss' ? ' gs-opt--on' : ''}`} {...optionProps('oss')}>
            <span className="gs-opt__icwrap">
              <span className="gs-opt__ic"><GithubGlyph /></span>
              {stars !== null && (
                <span className="gs-opt__stars" aria-label={`${stars} GitHub stars`}>{formatStars(stars)}</span>
              )}
            </span>
            <span className="gs-opt__body">
              <span className="gs-opt__name">dstack</span>
              <span className="gs-opt__desc">The open-source control plane that works across clouds, Kubernetes, and on-prem.</span>
            </span>
          </div>

          <div className={`gs-opt gs-opt--row${tab === 'sky' ? ' gs-opt--on' : ''}`} {...optionProps('sky')}>
            <span className="gs-opt__ic"><CloudUploadGlyph /></span>
            <span className="gs-opt__body">
              <span className="gs-opt__name">dstack Sky</span>
              <span className="gs-opt__desc">Access GPU marketplace, or bring your own clouds. Hosted and managed by us.</span>
            </span>
          </div>

          <div className={`gs-opt gs-opt--row${tab === 'ent' ? ' gs-opt--on' : ''}`} {...optionProps('ent')}>
            <span className="gs-opt__ic"><FingerprintGlyph /></span>
            <span className="gs-opt__body">
              <span className="gs-opt__name">Enterprise</span>
              <span className="gs-opt__desc">Self-hosted with SSO, air-gapped setup, dedicated support, and more.</span>
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
                <span className="gs-foot__note">
                  <span className="gs-foot__full">Use with your own clouds, Kubernetes, and on-prem clusters</span>
                  <span className="gs-foot__short">Use with your own clouds &amp; clusters</span>
                </span>
                <Button variant="primary" href={docsUrl('installation')} style={mainButtonStyle}>Install open-source</Button>
              </div>
            </div>
          </div>
        )}

        {/* dstack Sky: GPU marketplace + bring-your-own-clouds, equal columns; footer CTA. */}
        {tab === 'sky' && (
          <div className="gs-detail" key="sky">
            <div className="gs-box">
              {/* Two panes with tab-styled headers. Source order is header→list, header→list, so on
                  mobile (single column) each header sits directly above its own list; on desktop a
                  2-row grid (auto-flow column) puts both headers in a row and both lists beneath. */}
              <div className="gs-sky">
                <div className="gs-skyhalf"><span className="gs-skytab">GPU marketplace</span></div>
                <div className="gs-col">
                  <ul className="gs-col__list">
                    {gpuOffers.map(gpu => (
                      <li key={`${gpu.name} ${gpu.memory}`} className="gs-mkt__row">
                        <span className="gs-mkt__g"><span className="gs-mkt__name">{gpu.name}</span>{' '}{gpu.memory}</span>
                        <span className="gs-mkt__p">{gpu.price}/hr</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="gs-skyhalf"><span className="gs-skytab">Bring your own clouds</span></div>
                <div className="gs-col">
                  <ul className="gs-col__list">
                    {SKY_CLOUDS.map(cloud => (
                      <li key={cloud} className="gs-cloud"><CheckGlyph /><span>{cloud}</span></li>
                    ))}
                  </ul>
                </div>
              </div>
              <div className="gs-boxfoot">
                <span className="gs-foot__note">
                  <span className="gs-foot__full">Sign up to get $5 credit for on-demand and spot instances</span>
                  <span className="gs-foot__short">Sign up to get $5 in credits</span>
                </span>
                <Button variant="primary" href="https://sky.dstack.ai" target="_blank" iconName="external" iconAlign="right" style={mainButtonStyle}>Sign up</Button>
              </div>
            </div>
          </div>
        )}

        {/* Enterprise: the open-source box's tabbed shell, with a single "Extra" tab for now. */}
        {tab === 'ent' && (
          <div className="gs-detail" key="ent">
            <div className="gs-box">
              <div className="gs-tabs" role="tablist" aria-label="Enterprise">
                <span className="gs-tab gs-tab--on">Self-managed</span>
              </div>
              <div className="gs-entbody">
                <ul className="gs-caps">
                  {ENT_CAPS.map(cap => (
                    <li key={cap.title} className="gs-cap">
                      <span className="gs-cap__ic">{cap.icon}</span>
                      <span className="gs-cap__b">
                        <span className="gs-cap__t">{cap.title}</span>
                        <span className="gs-cap__s">{cap.sub}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="gs-boxfoot">
                <span className="gs-foot__note">
                  <span className="gs-foot__full">Talk to our team to get answers and a free trial</span>
                  <span className="gs-foot__short">Talk to our team for a free trial</span>
                </span>
                <Button variant="primary" href="https://calendly.com/dstackai/discovery-call" target="_blank" iconName="external" iconAlign="right" style={mainButtonStyle}>Contact us</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
