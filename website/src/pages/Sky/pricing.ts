// Indicative USD per GPU-hour from Sky API quotes, 2026-09-14; availability varies.
export const gpuPrices = [
  { name: 'B300', memory: '288GB', onDemand: '$7.58–17.80', spot: '$3.79–6.49' },
  { name: 'B200', memory: '192GB', onDemand: '$6.23–17.91', spot: '$2.41–5.44' },
  { name: 'H200', memory: '141GB', onDemand: '$4.20–9.89', spot: '$2.10–9.89' },
  { name: 'H100', memory: '80GB', onDemand: '$2.89–12.74', spot: '$1.09–8.94' },
  // Includes AMD Developer Cloud and Hot Aisle backend quotes.
  { name: 'MI300X', memory: '192GB', onDemand: '$1.99–2.99', spot: null },
  { name: 'RTX PRO 6000', memory: '96GB', onDemand: '$0.97–7.20', spot: '$0.50–3.17' },
  { name: 'A100', memory: '80GB', onDemand: '$1.59–5.58', spot: '$0.87–4.29' },
  { name: 'A100', memory: '40GB', onDemand: '$1.99–3.75', spot: '$0.34–3.57' },
  { name: 'L40S', memory: '48GB', onDemand: '$1.09–4.71', spot: '$0.54–4.71' },
];
