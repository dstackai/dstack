import Button from '@cloudscape-design/components/button';
import { mainButtonStyle } from '../../cloudscape-theme';
import { ContentTabs } from '../../components/ContentTabs';
import { ChipGlyph, CloudGlyph } from '../Home/GetStartedSection';
import { gpuPrices } from './pricing';

// Default marketplace clouds from dstack Sky's /api/backends/list_base_types.
const partnerGroups = [
  ['AWS', 'GCP'],
  ['Lambda', 'Runpod'],
  ['Verda', 'Nebius'],
];

export function MarketplaceTabs() {
  return (
    <ContentTabs
      ariaLabel="GPU marketplace"
      className="gs-box--compute"
      tabs={[
        {
          id: 'marketplace',
          label: 'Marketplace',
          className: 'gs-box--offers',
          content: (
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
          ),
          footer: (
            <span className="gs-foot__note">
              One account and unified billing across GPU clouds
            </span>
          ),
        },
        {
          id: 'partners',
          label: 'Partners',
          content: (
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
          ),
          footer: (
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
          ),
        },
      ]}
    />
  );
}
