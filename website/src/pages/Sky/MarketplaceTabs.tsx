import { KeyboardEvent, useId, useRef, useState } from 'react';
import Button from '@cloudscape-design/components/button';
import { mainButtonStyle } from '../../cloudscape-theme';
import { ChipGlyph, CloudGlyph } from '../Home/GetStartedSection';
import { gpuPrices } from './pricing';

// Default marketplace clouds from dstack Sky's /api/backends/list_base_types.
const partnerGroups = [
  ['AWS', 'GCP'],
  ['Lambda', 'Runpod'],
  ['Verda', 'Nebius'],
];

const tabs = ['Marketplace', 'Partners'];

export function MarketplaceTabs() {
  const [activeTab, setActiveTab] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useId();

  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const nextIndex = {
      ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index + tabs.length - 1) % tabs.length,
      Home: 0,
      End: tabs.length - 1,
    }[event.key];
    if (nextIndex === undefined) return;
    event.preventDefault();
    setActiveTab(nextIndex);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <div className={`gs-box gs-box--compute${activeTab === 0 ? ' gs-box--offers' : ''}`}>
      <div className="gs-tabs" role="tablist" aria-label="GPU marketplace">
        {tabs.map((label, index) => (
          <button
            key={label}
            ref={element => { tabRefs.current[index] = element; }}
            id={`${id}-tab-${index}`}
            type="button"
            role="tab"
            aria-selected={activeTab === index}
            aria-controls={`${id}-panel`}
            tabIndex={activeTab === index ? 0 : -1}
            className={`gs-tab${activeTab === index ? ' gs-tab--on' : ''}`}
            onClick={() => setActiveTab(index)}
            onKeyDown={event => onTabKeyDown(event, index)}
          >
            {label}
          </button>
        ))}
      </div>
      <div
        className="gs-skybody"
        id={`${id}-panel`}
        role="tabpanel"
        aria-labelledby={`${id}-tab-${activeTab}`}
        tabIndex={0}
      >
        {activeTab === 0 ? (
          <table className="sky-gpu-prices" aria-label="GPU prices in USD per GPU-hour">
            <thead>
              <tr>
                <th scope="col">GPU</th>
                <th scope="col">On-demand</th>
                <th scope="col">Spot</th>
              </tr>
            </thead>
            <tbody>
              {gpuPrices.map(gpu => (
                <tr key={`${gpu.name} ${gpu.memory}`}>
                  <th scope="row">
                    <span className="gs-mkt__left">
                      <span className="gs-li__ic"><ChipGlyph /></span>
                      <span className="gs-mkt__g"><span className="gs-mkt__name">{gpu.name}</span>{' '}{gpu.memory}</span>
                    </span>
                  </th>
                  <td>{gpu.onDemand}</td>
                  <td>{gpu.spot ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="gs-cloudcols">
            {partnerGroups.map(group => (
              <ul key={group[0]}>
                {group.map(partner => (
                  <li key={partner} className="gs-cloud">
                    <span className="gs-li__ic"><CloudGlyph /></span>
                    <span>{partner}</span>
                  </li>
                ))}
              </ul>
            ))}
          </div>
        )}
      </div>
      <div className="gs-boxfoot">
        {activeTab === 0 ? (
          <span className="gs-foot__note">
            One account and unified billing across GPU clouds
          </span>
        ) : (
          <>
            <span className="gs-foot__note">
              Offer your GPU capacity through dstack Sky
            </span>
            <Button
              href="https://calendly.com/dstackai/discovery-call"
              target="_blank"
              iconName="external"
              iconAlign="right"
              style={mainButtonStyle}
            >
              Become a partner
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
