// Image assets used across the site. The home hero is now a live <SquircleScene> component and
// the "Vendor-agnostic, open-source" architecture diagram is an HTML/CSS component (see
// components/ArchitectureDiagram.tsx) — neither is an image. The Old-page placeholders below are
// pulled from the Cloudscape foundation image set.
const img = (path: string) => `https://cloudscape.design${path}`;

export const images = {
  // Old page imagery (kept for comparison / as a template for future product pages).
  meet: img('/__images/yvlrib0vb3vb/3RkANdWu0IRLpTcBJYSPg5/2397551327a83cfbddd1fe4db9f58188/homepage--meet-cloudscape--os-light.png'),
  familiar: img('/__images/yvlrib0vb3vb/3CJGtMGSx07lhdtgwL8Ncb/0e33dc1bac3936239e2bc856ee268e80/homepage--get-familiar-with-system--os-light.png'),
  github: img('/__images/yvlrib0vb3vb/5WFt79VY8lv19rULhh7kss/a47ddc4dceb91f020910445feeebc306/homepage--cloudscape-on-github--os-light.png'),
  mode: img('/__images/yvlrib0vb3vb/6dN8hKQOPLKko1MdoXZWXc/b2a5390038d3a7e2604c2550a12c5641/foundation-overview--visual-modes--core-light.png'),
  theming: img('/__images/yvlrib0vb3vb/2GUtUNLAIC2tfIePMVbM4z/f054770207e01200a6e03f140c838437/foundation-overview--theming--os-light.png'),
  accessibility: img('/__images/yvlrib0vb3vb/1Bv6Ju9XwvoRt4YzZys5eI/cdc470297880845185849edb739cb5b6/foundation-overview--accessibility--vr-light.png'),
  responsive: img('/__images/yvlrib0vb3vb/4AYh8LuIrJO3AN0S0jtTzB/906ff95fd94ec7b20891e7327d1fc53f/foundation-overview--responsive-design--vr-light.png'),
} as const;

export type ThemedImage = { light: string; dark: string };
