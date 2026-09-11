import React from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import {
    AnchorNavigation,
    Box,
    BreadcrumbGroup,
    Button,
    Container,
    ContentLayout,
    ExpandableSection,
    Grid,
    Header,
    Icon,
    Link,
    Popover,
    SpaceBetween,
    TextContent,
} from 'components';

import { useAppSelector } from 'hooks';
import { ROUTES } from 'routes';
import { useGetUserDataQuery } from 'services/user';

import { Loading } from 'App/Loading';
import { selectAuthToken } from 'App/slice';

import styles from './styles.module.scss';

function OnThisPageNavigation({ variant }: { variant: 'mobile' | 'side' }) {
    const anchorNavigation = (
        <AnchorNavigation
            anchors={[
                {
                    text: 'Overview',
                    href: '#overview',
                    level: 1,
                },
                {
                    text: 'Features',
                    href: '#features',
                    level: 1,
                },
                {
                    text: 'Highlights',
                    href: '#highlights',
                    level: 1,
                },
                {
                    text: 'Documentation',
                    href: '#documentation',
                    level: 1,
                },
                {
                    text: 'Other versions',
                    href: '#other-versions',
                    level: 1,
                },
            ]}
            ariaLabelledby="navigation-header"
        />
    );

    return variant === 'side' ? (
        <div className={styles.onThisPageSide} data-testid="on-this-page">
            <Box variant="h2" margin={{ bottom: 'xxs' }}>
                <span id="navigation-header">On this page</span>
            </Box>
            {anchorNavigation}
        </div>
    ) : (
        <ExpandableSection variant="footer" headingTagOverride="h2" headerText="On this page">
            {anchorNavigation}
        </ExpandableSection>
    );
}

function HeroHeader() {
    const navigate = useNavigate();

    return (
        <Box data-testid="hero-header" padding={{ top: 'xs', bottom: 'l' }}>
            <Grid gridDefinition={[{ colspan: { default: 12, xs: 8, s: 9 } }, { colspan: { default: 12, xs: 4, s: 3 } }]}>
                <div>
                    <Box variant="h1">Welcome to dstack Sky</Box>
                    <Box variant="p" color="text-body-secondary" margin={{ top: 'xxs', bottom: 's' }}>
                        Enjoy the full power of <strong>dstack</strong> without the hassle of hosting it yourself or managing
                        your own infrastructure. <br />
                        Sign up for <strong>dstack Sky</strong> to use the cheapest GPUs from our marketplace or connect it to
                        your own cloud accounts.
                    </Box>
                </div>

                <Box margin={{ top: 'l' }}>
                    <SpaceBetween size="s">
                        <Button
                            fullWidth
                            href={ROUTES.AUTH.LOGIN}
                            onFollow={(event) => {
                                event.preventDefault();
                                navigate(ROUTES.AUTH.LOGIN);
                            }}
                            variant="primary"
                        >
                            Get started
                        </Button>
                        <Box fontSize="body-s" color="text-body-secondary" textAlign="center">
                            Sign up to get $5 credit
                        </Box>
                    </SpaceBetween>
                </Box>
            </Grid>
        </Box>
    );
}

function ProductOverview() {
    return (
        <section className={styles.pageSection} aria-label="Product overview">
            <SpaceBetween size="m">
                <Header variant="h2">
                    <span id="overview">Overview</span>
                </Header>
                <div>
                    <Box variant="p">
                        <strong>dstack</strong> is an open-source container orchestrator that lets ML teams easily manage
                        clusters, volumes, dev environments, training, and inference. Its container-native interface boosts
                        productivity, maximizes GPU efficiency, and lowers costs.
                    </Box>
                    <Box variant="p">
                        <strong>dstack Sky</strong> adds a managed service, letting you use the cheapest GPUs from our
                        marketplace or connect your own cloud accounts.
                    </Box>
                </div>

                <div>
                    <Box variant="h3" margin={{ bottom: 'xs' }}>
                        <span id="features">Features</span>
                    </Box>
                    <Box>
                        <dl className={styles.productDetails} aria-label="Product details">
                            <dt></dt>
                            <dt>
                                <Link
                                    href="https://github.com/dstackai/dstack"
                                    target="_blank"
                                    external={true}
                                    variant="primary"
                                >
                                    Open-source
                                </Link>
                            </dt>
                            <dt>dstack Sky</dt>

                            <dd>
                                Bring your own cloud{' '}
                                <Popover
                                    header="Bring your own cloud (BYOC)"
                                    content={
                                        <>
                                            <Box variant="p">
                                                Use compute from your own cloud account(s) by providing your credentials.
                                            </Box>
                                            <Box variant="p">
                                                You pay for compute and storage usage directly to the configured cloud
                                                provider(s) through their billing. <code>dstack</code> won't bill or charge you.
                                            </Box>
                                        </>
                                    }
                                >
                                    <Link variant="info">
                                        <Icon name="status-info" size="small" />
                                    </Link>
                                </Popover>
                            </dd>
                            <dd>
                                <Icon name="check" />
                            </dd>
                            <dd>
                                <Icon name="check" />
                            </dd>

                            <dd>
                                GPU marketplace{' '}
                                <Popover
                                    header="GPU marketplace"
                                    content={
                                        <>
                                            <Box variant="p">
                                                Use compute from multiple cloud providers without needing your own cloud
                                                account(s).
                                            </Box>
                                            <Box variant="p">
                                                You pay for compute and storage usage directly to <code>dstack</code>. You can
                                                top up your balance in your <code>dstack</code> user settings.
                                            </Box>
                                            <Box variant="p">When you sign up, you get $5 in credits.</Box>
                                        </>
                                    }
                                >
                                    <Link variant="info">
                                        <Icon name="status-info" size="small" />
                                    </Link>
                                </Popover>
                            </dd>
                            <dd></dd>
                            <dd>
                                <Icon name="check" />
                            </dd>

                            <dd>
                                SSH fleets{' '}
                                <Popover
                                    header="SSH fleets"
                                    content="If you have a group of on-prem servers accessible via SSH, you can create an SSH fleet."
                                >
                                    <Link variant="info">
                                        <Icon name="status-info" size="small" />
                                    </Link>
                                </Popover>
                            </dd>
                            <dd>
                                <Icon name="check" />
                            </dd>
                            <dd>
                                <Icon name="check" />
                            </dd>

                            <dd>
                                Gateway{' '}
                                <Popover
                                    header="Gateway endpoint"
                                    content="If you want services to auto-scale and be accessible on a custom domain, you can create a gateway and map it to your custom domain."
                                >
                                    <Link variant="info">
                                        <Icon name="status-info" size="small" />
                                    </Link>
                                </Popover>
                            </dd>
                            <dd>Configure your own domain</dd>
                            <dd>
                                Pre-configured <code>*.sky.dstack.ai</code>
                            </dd>

                            <dd>Pricing</dd>
                            <dd>Free</dd>
                            <dd>Pay only if you use GPU marketplace</dd>

                            <dd></dd>
                            <dd>Self-hosted</dd>
                            <dd>Hosted by dstack</dd>
                        </dl>
                    </Box>
                </div>

                <div>
                    <Header variant="h3">
                        <span id="highlights">Highlights</span>
                    </Header>
                    <TextContent>
                        <ul>
                            <li>Use compute from your own cloud account(s) or through GPU marketplace.</li>
                            <li>Create dev environments, run training tasks, and deploy inference services.</li>
                            <li>Manage volumes and fleets.</li>
                            <li>Manage multiple projects and teams.</li>
                        </ul>
                    </TextContent>
                </div>

                <div>
                    <Header variant="h3">
                        <span id="documentation">Documentation</span>
                    </Header>
                    <SpaceBetween size="m">
                        <Box variant="p">
                            Want to learn more about <strong>dstack</strong>? Check out the{' '}
                            <Link href="https://dstack.ai/docs/" variant="primary" external={true}>
                                documentation
                            </Link>
                        </Box>
                    </SpaceBetween>
                </div>
            </SpaceBetween>
        </section>
    );
}

function OtherVersions() {
    return (
        <section className={styles.otherVersions}>
            <Box variant="h2" margin={{ bottom: 'm' }}>
                <span id="other-versions">Other versions</span>
            </Box>
            <ul className={styles.productCardsList}>
                <li className={styles.productCardsListItem} aria-label="Open-source">
                    <Container>
                        <SpaceBetween direction="vertical" size="s">
                            <SpaceBetween direction="vertical" size="xxs">
                                <Box variant="h3">Open-source</Box>
                                <Box variant="small">Self-hosted</Box>
                            </SpaceBetween>
                            <Box variant="p">Fully customizable and self-hosted open-source version.</Box>
                            <Button external={true} href="https://dstack.ai/docs/installation">
                                Installation
                            </Button>
                        </SpaceBetween>
                    </Container>
                </li>
                <li className={styles.productCardsListItem} aria-label="dstack Factory">
                    <Container>
                        <SpaceBetween direction="vertical" size="s">
                            <SpaceBetween direction="vertical" size="xxs">
                                <Box variant="h3">dstack Factory</Box>
                                <Box variant="small">Self-hosted</Box>
                            </SpaceBetween>
                            <Box variant="p">Single sign-on, advanced governance controls, and dedicated support.</Box>
                            <Button variant="primary" external={true} href="https://calendly.com/dstackai/discovery-call">
                                Book a demo
                            </Button>
                        </SpaceBetween>
                    </Container>
                </li>
            </ul>
        </section>
    );
}

export const Home: React.FC = () => {
    const token = useAppSelector(selectAuthToken);
    const localStorageIsAvailable = 'localStorage' in window;
    const {
        currentData: userData,
        error,
        isFetching,
    } = useGetUserDataQuery({ token }, { skip: !token || !localStorageIsAvailable });

    if (token && localStorageIsAvailable && isFetching && !userData) return <Loading />;
    if (token && localStorageIsAvailable && userData?.username && !error) {
        return <Navigate replace to={ROUTES.RUNS.LIST} />;
    }

    return (
        <ContentLayout
            breadcrumbs={
                <BreadcrumbGroup
                    items={[
                        { href: 'https://dstack.ai', text: 'dstack' },
                        { href: '#', text: 'dstack Sky' },
                    ]}
                    expandAriaLabel="Show path"
                    ariaLabel="Breadcrumbs"
                />
            }
            headerVariant="high-contrast"
            header={<HeroHeader />}
            defaultPadding={true}
            maxContentWidth={1040}
            disableOverlap={true}
        >
            <div className={styles.productPageContentGrid}>
                <div className={styles.onThisPageMobile}>
                    <OnThisPageNavigation variant="mobile" />
                </div>

                <aside aria-label="Side bar" className={styles.productPageAside}>
                    <div className={styles.productPageAsideSticky}>
                        <SpaceBetween size="xl">
                            <div className={styles.onThisPageMobile}>
                                <OnThisPageNavigation variant="side" />
                            </div>
                        </SpaceBetween>
                    </div>
                </aside>

                <main className={styles.productPageContent}>
                    <ProductOverview />
                    <OtherVersions />
                </main>
            </div>
        </ContentLayout>
    );
};
