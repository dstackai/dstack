import { Fragment, useId, useState } from 'react';
import CodeView from '@cloudscape-design/code-view/code-view';
import shHighlight from '@cloudscape-design/code-view/highlight/sh';
import Button from '@cloudscape-design/components/button';
import { asset } from '../../asset';
import { mainButtonStyle } from '../../cloudscape-theme';
import { BoxGlyph, CloudGlyph, LayersGlyph } from '../../components/Capabilities';
import { ContentTabs } from '../../components/ContentTabs';
import { highlightTerms } from '../../components/highlightTerms';
import { installMethods, maxInstallLines, padYamlToLines } from '../../data/snippets';
import { DOCS_URL, ROUTES, docsUrl } from '../../routes';
import { FactoryGetStartedTabs } from '../Factory/FactoryGetStartedTabs';
import { MarketplaceTabs } from '../Sky/MarketplaceTabs';

// Product menus in SiteNavigation.tsx and mkdocs/overrides/header-2.html use a shorter
// dstack description.
const products = [
  {
    id: 'dstack',
    name: 'dstack',
    description: 'A unified orchestration interface across GPU clouds, Kubernetes, VMs, and bare-metal clusters.',
    group: 'Self-hosted',
    icon: <BoxGlyph />,
  },
  {
    id: 'factory',
    name: 'dstack Factory',
    description: 'A multi-tenant orchestration stack for AI labs, data centers, and AI token factories.',
    group: 'Self-hosted',
    icon: <LayersGlyph />,
  },
  {
    id: 'sky',
    name: 'dstack Sky',
    description: 'Unified access to GPU clouds. Better prices and one billing.',
    group: 'Hosted by us',
    icon: <CloudGlyph />,
  },
] as const;

type ProductId = (typeof products)[number]['id'];

export function GetStartedSection() {
  const [product, setProduct] = useState<ProductId>('dstack');
  const id = useId();
  const footer = <ProductFooter product={product} />;

  return (
    <section className="docs-section" id="resources">
      <h2>Get started</h2>

      <div className="gs-deploy">
        <div className="gs-rail" role="group" aria-label="Choose a product">
          {products.map((option, index) => (
            <Fragment key={option.id}>
              {option.group !== products[index - 1]?.group && (
                <div className="gs-rail__group">{option.group}</div>
              )}
              <button
                type="button"
                id={`${id}-${option.id}`}
                className={`gs-opt ${option.id === 'dstack' ? 'gs-opt--feat' : 'gs-opt--row'}${product === option.id ? ' gs-opt--on' : ''}`}
                aria-pressed={product === option.id}
                aria-controls={`${id}-detail`}
                onClick={() => setProduct(option.id)}
              >
                <span className="gs-opt__ic">{option.icon}</span>
                <span className="gs-opt__body">
                  <span className="gs-opt__name">{option.name}</span>
                  <span className="gs-opt__desc">{option.description}</span>
                </span>
              </button>
            </Fragment>
          ))}
        </div>

        <div className="gs-detail" id={`${id}-detail`} role="region" aria-labelledby={`${id}-${product}`}>
          {product === 'dstack' && (
            <ContentTabs
              ariaLabel="Install method"
              className="gs-box--install"
              tabs={installMethods.map(method => ({
                id: method.id,
                label: method.label,
                content: <ShellCode content={padYamlToLines(method.code, maxInstallLines)} />,
                footer,
              }))}
            />
          )}
          {product === 'factory' && <FactoryGetStartedTabs footer={footer} />}
          {product === 'sky' && <MarketplaceTabs marketplaceOnly footer={footer} />}
        </div>
      </div>
    </section>
  );
}

function ProductFooter({ product }: { product: ProductId }) {
  if (product === 'dstack') {
    return (
      <>
        <span className="gs-foot__note">
          {highlightTerms('Set up the dstack server and bring your own compute')}
        </span>
        <div className="gs-foot__actions">
          <Button variant="primary" href={docsUrl('installation')} style={mainButtonStyle}>Install open-source</Button>
          <Button href={DOCS_URL} style={mainButtonStyle}>View docs</Button>
        </div>
      </>
    );
  }

  const isSky = product === 'sky';
  return (
    <>
      <span className="gs-foot__note">
        {highlightTerms(
          isSky
            ? 'All in dstack Factory, plus on-demand GPUs from our marketplace'
            : 'All in dstack, plus multi-tenancy, billing, and serverless',
        )}
      </span>
      <div className="gs-foot__actions">
        <Button
          variant="primary"
          href={isSky ? 'https://sky.dstack.ai/' : 'https://calendly.com/dstackai/discovery-call'}
          target="_blank"
          iconName="external"
          iconAlign="right"
          style={mainButtonStyle}
        >
          {isSky ? 'Sign up' : 'Book a demo'}
        </Button>
        <Button href={asset(isSky ? ROUTES.SKY : ROUTES.FACTORY)} style={mainButtonStyle}>Learn more</Button>
      </div>
    </>
  );
}

// Keep padded snippets the same height across installation tabs.
function ShellCode({ content }: { content: string }) {
  return (
    <div className="code-snippet">
      <CodeView ariaLabel="Installation commands" content={content} highlight={shHighlight} />
    </div>
  );
}
