import React from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import enMessages from '@cloudscape-design/components/i18n/messages/all.en.json';
import { Mode } from '@cloudscape-design/global-styles';

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
    I18nProvider,
    Icon,
    Link,
    Popover,
    SpaceBetween,
    TextContent,
    TopNavigation,
} from 'components';
import { DarkThemeIcon, LightThemeIcon } from 'layouts/AppLayout/themeIcons';

import { DISCORD_URL } from 'consts';
import { useAppDispatch, useAppSelector } from 'hooks';
import { goToUrl } from 'libs';
import { ROUTES } from 'routes';
import { useGithubAuthorizeMutation } from 'services/auth';

import { selectSystemMode, setSystemMode } from 'App/slice';

import logo from 'assets/images/logo.svg';
import styles from './styles.module.scss';

type PortalProps = {
    children: React.ReactNode;
};

const i18nStrings = {
    overflowMenuTriggerText: '',
    overflowMenuTitleText: '',
    overflowMenuBackIconAriaLabel: '',
    overflowMenuDismissIconAriaLabel: '',
};

const THEME_ICON_MAP: Record<Mode, React.FC> = {
    [Mode.Dark]: DarkThemeIcon,
    [Mode.Light]: LightThemeIcon,
};

const GitHubIcon: React.FC = () => (
    <span>
        <svg viewBox="0 0 14 14" stroke="none" xmlns="http://www.w3.org/2000/svg">
            <path
                d="M7 0.34375C6.125 0.34375 5.27083 0.510417 4.4375 0.84375C3.625 1.17708 2.90625 1.65625 2.28125 2.28125C1.65625 2.90625 1.17708 3.63542 0.84375 4.46875C0.510417 5.28125 0.34375 6.125 0.34375 7C0.34375 8.45833 0.760417 9.77083 1.59375 10.9375C2.44792 12.0833 3.55208 12.8854 4.90625 13.3438C5.05208 13.3646 5.15625 13.3333 5.21875 13.25C5.30208 13.1875 5.34375 13.1042 5.34375 13V11.875C4.57292 12.0417 3.96875 11.9375 3.53125 11.5625C3.30208 11.3958 3.15625 11.1979 3.09375 10.9688C3.01042 10.7396 2.89583 10.5417 2.75 10.375C2.66667 10.25 2.57292 10.1562 2.46875 10.0938L2.34375 10C2.17708 9.875 2.09375 9.78125 2.09375 9.71875C2.09375 9.65625 2.14583 9.625 2.25 9.625L2.40625 9.59375C2.67708 9.61458 2.92708 9.73958 3.15625 9.96875C3.28125 10.0729 3.36458 10.1771 3.40625 10.2812C3.67708 10.7188 4.03125 10.9583 4.46875 11C4.73958 11.0208 5.04167 10.9688 5.375 10.8438C5.41667 10.4479 5.55208 10.1458 5.78125 9.9375C4.86458 9.83333 4.17708 9.58333 3.71875 9.1875C3.07292 8.64583 2.75 7.80208 2.75 6.65625C2.75 5.96875 2.97917 5.375 3.4375 4.875C3.35417 4.6875 3.3125 4.47917 3.3125 4.25C3.27083 3.875 3.33333 3.48958 3.5 3.09375H3.6875C3.85417 3.09375 4.05208 3.13542 4.28125 3.21875C4.61458 3.34375 4.96875 3.53125 5.34375 3.78125C5.86458 3.63542 6.41667 3.5625 7 3.5625C7.58333 3.5625 8.13542 3.63542 8.65625 3.78125C9.19792 3.42708 9.66667 3.20833 10.0625 3.125C10.2708 3.08333 10.4167 3.07292 10.5 3.09375C10.6667 3.48958 10.7292 3.875 10.6875 4.25C10.6875 4.47917 10.6458 4.6875 10.5625 4.875C11.0208 5.375 11.25 5.96875 11.25 6.65625C11.25 7.82292 10.9271 8.66667 10.2812 9.1875C9.80208 9.58333 9.11458 9.83333 8.21875 9.9375C8.51042 10.2083 8.65625 10.625 8.65625 11.1875V13C8.65625 13.1042 8.6875 13.1875 8.75 13.25C8.83333 13.3333 8.95833 13.3646 9.125 13.3438C10.4583 12.8854 11.5417 12.0833 12.375 10.9375C13.2292 9.77083 13.6562 8.45833 13.6562 7C13.6562 6.125 13.4896 5.28125 13.1562 4.46875C12.8229 3.63542 12.3438 2.90625 11.7188 2.28125C11.0938 1.65625 10.3646 1.17708 9.53125 0.84375C8.71875 0.510417 7.875 0.34375 7 0.34375Z"
                fill="currentColor"
            />
        </svg>
    </span>
);

const askAi = () => {
    window.document.body.focus();
    window?.Kapa?.open();
};

const HeaderPortal = ({ children }: PortalProps) => {
    const domNode = document.querySelector('#header');
    if (domNode) return createPortal(children, domNode);
    return null;
};

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
    const [githubAuthorize, { isLoading }] = useGithubAuthorizeMutation();

    const signInClick = () => {
        githubAuthorize()
            .unwrap()
            .then((data) => {
                goToUrl(data.authorization_url);
            })
            .catch(console.log);
    };

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
                    <Box color="text-body-secondary">
                        By clicking <strong>Sign up</strong> you agree to the{' '}
                        <Link href="https://dstack.ai/terms/" target="_blank" external={true} variant="primary">
                            Terms
                        </Link>{' '}
                        and{' '}
                        <Link href="https://dstack.ai/privacy/" target="_blank" external={true} variant="primary">
                            Privacy policy
                        </Link>
                    </Box>
                </div>

                <Box margin={{ top: 'l' }}>
                    <SpaceBetween size="s">
                        <Button
                            fullWidth={true}
                            onClick={signInClick}
                            disabled={isLoading}
                            variant="primary"
                            iconSvg={<GitHubIcon />}
                        >
                            Sign up with GitHub
                        </Button>

                        <Box fontSize="body-s" color="text-body-secondary" textAlign="center">
                            No credit card required
                        </Box>
                    </SpaceBetween>

                    <br />

                    <SpaceBetween size="s">
                        <Button fullWidth={true} onClick={signInClick} disabled={isLoading} iconSvg={<GitHubIcon />}>
                            Sign in with GitHub
                        </Button>

                        <Button fullWidth={true} href={ROUTES.AUTH.TOKEN} iconName="key">
                            Sign in with a token
                        </Button>
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

                            <dd>Your cloud accounts</dd>
                            <dd>
                                <Icon name="check" />
                            </dd>
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
                                GPU marketplace{' '}
                                <Popover
                                    header="GPU marketplace"
                                    content="dstack Sky offers the cheapest cloud GPU offers from a variety of supported providers.
                                    You pay directly to dstack Sky for GPU usage."
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
                            <dd>Pre-configured *.sky.dstack.ai</dd>

                            <dd>Pricing</dd>
                            <dd>Free</dd>
                            <dd>Pay only for marketplace GPU</dd>

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
                            <li>Use your own cloud accounts or access the cheapest GPUs from our marketplace.</li>
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
                <li className={styles.productCardsListItem} aria-label="dstack Enterprise">
                    <Container>
                        <SpaceBetween direction="vertical" size="s">
                            <SpaceBetween direction="vertical" size="xxs">
                                <Box variant="h3">dstack Enterprise</Box>
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

export const LoginByGithub: React.FC = () => {
    const { t } = useTranslation();
    const dispatch = useAppDispatch();
    const systemMode = useAppSelector(selectSystemMode) ?? '';
    const ThemeIcon = THEME_ICON_MAP[systemMode];

    const onChangeSystemModeToggle = (event: React.MouseEvent<HTMLButtonElement>) => {
        event.preventDefault();
        switch (systemMode) {
            case Mode.Light:
                dispatch(setSystemMode(Mode.Dark));
                return;
            default:
                dispatch(setSystemMode(Mode.Light));
        }
    };

    return (
        <>
            <HeaderPortal>
                <div>
                    <TopNavigation
                        i18nStrings={i18nStrings}
                        identity={{
                            href: 'https://dstack.ai',
                            logo: { src: logo, alt: 'Dstack logo' },
                        }}
                        utilities={[
                            {
                                type: 'button',
                                text: t('common.docs'),
                                external: true,
                                onClick: () => goToUrl('https://dstack.ai/docs/', true),
                            },
                            {
                                type: 'button',
                                text: t('common.discord'),
                                external: true,
                                onClick: () => goToUrl(DISCORD_URL, true),
                            },
                            {
                                href: 'theme-button',
                                type: 'button',
                                iconSvg: <ThemeIcon />,
                                onClick: onChangeSystemModeToggle,
                            },
                            {
                                type: 'button',
                                iconName: 'gen-ai',
                                text: t('common.ask_ai'),
                                title: t('common.ask_ai'),
                                onClick: askAi,
                            },
                        ]}
                    />
                </div>
            </HeaderPortal>

            <I18nProvider locale="en" messages={[enMessages]}>
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
            </I18nProvider>
        </>
    );
};
