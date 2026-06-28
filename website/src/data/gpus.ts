// Rough per-GPU/hour price ranges across backends, in the spirit of `dstack offer --group-by gpu`.
// Single source of truth, shared by the "Access marketplace GPUs" block (ExploreSection) and the
// dstack Sky "GPU marketplace" pane (GetStartedSection). Prices use a compact en-dash range; a
// "/hr" suffix is appended at render time.
export const gpuOffers = [
  { name: 'B300', memory: '288GB', price: '$6.00–12.00' },
  { name: 'B200', memory: '192GB', price: '$4.00–9.00' },
  { name: 'H200', memory: '141GB', price: '$3.10–7.49' },
  { name: 'H100', memory: '80GB', price: '$1.90–5.99' },
  { name: 'RTX PRO 6000', memory: '96GB', price: '$1.79–3.50' },
  { name: 'A100', memory: '80GB', price: '$1.20–3.40' },
  { name: 'A100', memory: '40GB', price: '$0.83–2.30' },
  { name: 'L40S', memory: '48GB', price: '$0.80–1.40' },
];
