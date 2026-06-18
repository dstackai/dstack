import Box from '@cloudscape-design/components/box';
import Container from '@cloudscape-design/components/container';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { asset } from '../../asset';

const testimonials = [
  {
    name: 'Wah Loon Keng',
    title: 'Sr. AI Engineer',
    company: 'Electronic Arts',
    photo: '/static/quotes/keng.png',
    quote:
      'With dstack, AI researchers at EA can spin up and scale experiments without touching infrastructure. It supports everything from quick prototyping to multi-node training on any cloud.',
  },
  /* Replaced Aleksandr Movchan, kept hidden for reference:
  {
    name: 'Aleksandr Movchan',
    title: 'ML Engineer',
    company: 'Mobius Labs',
    photo: '/static/quotes/movchan.jpg',
    quote:
      'Thanks to dstack, my team can quickly tap into affordable GPUs and streamline our workflows from testing and development to full-scale application deployment.',
  },
  */
  {
    name: 'Konstantin Willeke',
    title: 'AI Researcher',
    company: 'Metamorphic',
    photo: '/static/quotes/konstantin.png',
    quote:
      'Fantastic tool if you have heterogeneous compute across different clusters or clouds. dstack ties it all together behind one interface, so we can run experiments without rethinking our setup.',
  },
  /* Replaced Alvaro Bartolome, kept hidden for reference:
  {
    name: 'Alvaro Bartolome',
    title: 'ML Engineer',
    company: 'Argilla',
    photo: '/static/quotes/alvarobartt.jpg',
    quote:
      "With dstack it's incredibly easy to define a configuration within a repository and run it without worrying about GPU availability. It lets you focus on data and your research.",
  },
  */
  {
    name: 'Dmitry Melikyan',
    title: 'Founder',
    company: 'Graphsignal',
    photo: '/static/quotes/dmitry.jpg',
    quote:
      "dstack gives us a unified layer for GPU development and inference across on-prem systems and GPU clouds. It's one workflow from local experiments to production — no custom orchestration to build or maintain for each environment.",
  },
  {
    name: 'Park Chansung',
    title: 'ML Researcher',
    company: 'ETRI',
    photo: '/static/quotes/chansung.jpg',
    quote:
      'Thanks to dstack, I can effortlessly access the top GPU options across different clouds, saving me time and money while pushing my AI work forward.',
  },
  /* Replaced Eckart Burgwedel, kept hidden for reference:
  {
    name: 'Eckart Burgwedel',
    title: 'CEO',
    company: 'Uberchord',
    photo: '/static/quotes/eckart.png',
    quote:
      'With dstack, running LLMs on a cloud GPU is as easy as running a local Docker container. It combines the ease of Docker with the auto-scaling capabilities of K8S.',
  },
  */
  {
    name: 'Nikita Shupeyko',
    title: 'AI Infra',
    company: 'Toffee',
    photo: '/static/quotes/nikita.jpeg',
    quote:
      "Since we switched to dstack, we've cut the overhead of GPU-cloud orchestration by more than 50%. Running across multiple GPU clouds from a single config also let us reduce our effective GPU spend by 2–3×.",
  },
  {
    name: 'Jon Stevens',
    title: 'CEO',
    company: 'Hot Aisle',
    photo: '/static/quotes/jon.jpeg',
    quote:
      "dstack's advantages over Slurm are clear: it's a modern, ground-up approach to running workloads at scale. If you're choosing an orchestration platform, dstack is the place to start.",
  },
];

// Social proof: a grid of customer testimonials shown above the "Get started" section.
export function TrustedBySection() {
  return (
    <section className="docs-section" id="trusted-by">
      <h2>Trusted by AI teams</h2>
      <div className="testimonial-grid">
        {testimonials.map(testimonial => (
          <Container key={testimonial.name} fitHeight>
            <SpaceBetween size="s">
              <div className="testimonial-person">
                <img className="testimonial-photo" src={asset(testimonial.photo)} alt="" />
                <SpaceBetween size="xxxs">
                  <Box variant="h3" padding="n">{testimonial.name}</Box>
                  <Box variant="small" color="text-body-secondary">
                    {testimonial.title} at {testimonial.company}
                  </Box>
                </SpaceBetween>
              </div>
              <Box variant="p">{testimonial.quote}</Box>
            </SpaceBetween>
          </Container>
        ))}
      </div>
    </section>
  );
}
