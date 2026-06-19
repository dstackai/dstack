import CodeView from '@cloudscape-design/code-view/code-view';
import shHighlight from '@cloudscape-design/code-view/highlight/sh';
import Button from '@cloudscape-design/components/button';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Tabs from '@cloudscape-design/components/tabs';
import { mainButtonStyle } from '../../cloudscape-theme';
import { AlternatingDocBlock } from '../../components/AlternatingDocBlock';
import { installMethods, maxInstallLines, padYamlToLines } from '../../data/snippets';
import { docsUrl } from '../../routes';

// Read-only shell snippet. Line wrapping is left off so padded snippets stay
// equal height across tabs (see padYamlToLines).
function ShellCode({ content }: { content: string }) {
  return (
    <div className="code-snippet">
      <CodeView ariaLabel="Installation commands" content={content} highlight={shHighlight} />
    </div>
  );
}

// Closing "Get started" section: the open-source install path, then the hosted/enterprise
// options under "Looking for more?".
export function GetStartedSection() {
  return (
    <section className="docs-section" id="resources">
      <h2>Get started</h2>

      <AlternatingDocBlock
        visual={
          <Tabs
            variant="container"
            ariaLabel="Install method"
            tabs={installMethods.map(method => ({
              id: method.id,
              label: method.label,
              content: <ShellCode content={padYamlToLines(method.code, maxInstallLines)} />,
            }))}
          />
        }
        title="Open-source"
        imageFirst
        action={
          <SpaceBetween direction="horizontal" size="xs">
            <Button href={docsUrl('quickstart')} style={mainButtonStyle}>Quickstart</Button>
          </SpaceBetween>
        }
      >
        Install dstack on your laptop with uv, or deploy it anywhere using the dstackai/dstack Docker image.

        <br />
        <br />

        It takes under a minute to get started and have your first workload running whether you're
        using dstack via CLI, or let agents do it for you.
      </AlternatingDocBlock>

      <AlternatingDocBlock
        visual={
          <div className="product-grid product-grid--pair">
            <article className="figma-card">
              <div>
                <h3>dstack Sky</h3>
                <p>Hosted by us. Bring your own clouds, or access marketplace GPUs.</p>
                <Button href="https://sky.dstack.ai" variant="primary" target="_blank" iconName="external" iconAlign="right" style={mainButtonStyle}>
                  Sign up
                </Button>
              </div>
            </article>
            <article className="figma-card">
              <div>
                <h3>dstack Enterprise</h3>
                <p>Self-hosted with SSO, air-gapped setup, dedicated support, and more.</p>
                <Button href="https://calendly.com/dstackai/discovery-call" target="_blank" iconName="external" iconAlign="right" style={mainButtonStyle}>
                  Talk to us
                </Button>
              </div>
            </article>
          </div>
        }
        title="Looking for more?"
      >
        We can host and operate dstack for you, or back your own self-hosted deployment with enterprise security and support.
      </AlternatingDocBlock>
    </section>
  );
}
