import React from 'react';
import Avatar from 'react-avatar';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import { Mode } from '@cloudscape-design/global-styles';

import {
    AppLayout as GenericAppLayout,
    AppLayoutProps as GenericAppLayoutProps,
    BreadcrumbGroup,
    HelpPanel,
    Notifications,
    SideNavigation,
    Tabs,
    TopNavigation,
} from 'components';

import { DISCORD_URL, DOCS_URL } from 'consts';
import { useAppDispatch, useAppSelector } from 'hooks';
import { goToUrl } from 'libs';
import { ROUTES } from 'routes';
import { useGetServerInfoQuery } from 'services/server';

import {
    closeToolsPanel,
    openTutorialPanel,
    selectBreadcrumbs,
    selectHelpPanelContent,
    selectSystemMode,
    selectToolsPanelState,
    selectUserName,
    setSystemMode,
    setToolsTab,
} from 'App/slice';

import { AnnotationContext } from './AnnotationContext';
import { useSideNavigation } from './hooks';
import { TallyComponent } from './Tally';
import { DarkThemeIcon, LightThemeIcon } from './themeIcons';
import { TutorialPanel } from './TutorialPanel';

import { ToolsTabs } from 'App/types';

import logo from 'assets/images/logo.svg';
import styles from './index.module.scss';

type PortalProps = { children: React.ReactNode };

const HeaderPortal = ({ children }: PortalProps) => {
    const domNode = document.querySelector('#header');
    if (domNode) return createPortal(children, domNode);
    return null;
};

const THEME_ICON_MAP: Record<Mode, React.FC> = {
    [Mode.Dark]: DarkThemeIcon,
    [Mode.Light]: LightThemeIcon,
};

const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    useGetServerInfoQuery();

    const userName = useAppSelector(selectUserName) ?? '';
    const systemMode = useAppSelector(selectSystemMode) ?? '';
    const breadcrumbs = useAppSelector(selectBreadcrumbs);
    const { isOpen: toolsIsOpen, tab: toolsActiveTab } = useAppSelector(selectToolsPanelState);
    const helpPanelContent = useAppSelector(selectHelpPanelContent);
    const dispatch = useAppDispatch();
    const { navLinks, activeHref } = useSideNavigation();

    const onFollowHandler: SideNavigationProps['onFollow'] = (event) => {
        event.preventDefault();

        if (event.detail.external) {
            goToUrl(event.detail.href, true);
        } else {
            navigate(event.detail.href);
        }
    };

    const renderBreadcrumbs = () => {
        if (breadcrumbs) return <BreadcrumbGroup items={breadcrumbs} onFollow={onFollowHandler} />;
    };

    const i18nStrings = {
        overflowMenuTriggerText: '',
        overflowMenuTitleText: '',
        overflowMenuBackIconAriaLabel: '',
        overflowMenuDismissIconAriaLabel: '',
    };

    const profileActions = [
        { type: 'button', href: ROUTES.USER.DETAILS.FORMAT(userName), id: 'settings', text: t('common.settings') },
        { type: 'button', href: ROUTES.LOGOUT, id: 'signout', text: t('common.sign_out') },
    ];

    const onChangeToolHandler: GenericAppLayoutProps['onToolsChange'] = ({ detail: { open } }) => {
        if (!open) dispatch(closeToolsPanel());
    };

    const onChangeToolsTab = (tabName: ToolsTabs) => {
        dispatch(setToolsTab(tabName));
    };

    const toggleTutorialPanel = () => {
        if (process.env.UI_VERSION !== 'sky') {
            return;
        }

        if (toolsIsOpen) {
            dispatch(closeToolsPanel());
            return;
        }

        dispatch(openTutorialPanel());
    };

    const isVisibleInfoTab = helpPanelContent.header || helpPanelContent.footer || helpPanelContent.body;

    const avatarProps = process.env.UI_VERSION === 'enterprise' ? { name: userName } : { githubHandle: userName };

    const onChangeSystemModeToggle: SideNavigationProps['onFollow'] = (event) => {
        event.preventDefault();

        switch (systemMode) {
            case Mode.Light:
                dispatch(setSystemMode(Mode.Dark));
                return;
            default:
                dispatch(setSystemMode(Mode.Light));
        }
    };

    const ThemeIcon = THEME_ICON_MAP[systemMode];

    const askAi = () => {
        window.document.body.focus();
        window?.Kapa?.open();
    };

    return (
        <AnnotationContext>
            <HeaderPortal>
                <div className={styles.appHeader}>
                    <TopNavigation
                        i18nStrings={i18nStrings}
                        identity={{
                            href: '/',
                            logo: { src: logo, alt: 'Dstack logo' },
                        }}
                        utilities={[
                            {
                                type: 'button',
                                text: t('common.docs'),
                                external: true,
                                onClick: () => goToUrl(DOCS_URL, true),
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
                            process.env.UI_VERSION === 'sky' && {
                                type: 'button',
                                iconName: 'gen-ai',
                                text: t('common.ask_ai'),
                                title: t('common.ask_ai'),
                                onClick: askAi,
                            },
                            process.env.UI_VERSION === 'sky' && {
                                type: 'button',
                                iconName: 'suggestions',
                                title: t('common.tutorial_other'),
                                onClick: toggleTutorialPanel,
                            },
                            {
                                'data-class': 'user-menu',
                                type: 'menu-dropdown',
                                text: (
                                    <div className={styles.userAvatar}>
                                        <Avatar {...avatarProps} size="40px" />
                                    </div>
                                ),
                                items: profileActions,
                                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                                // @ts-ignore
                                onItemFollow: onFollowHandler,
                            },
                        ].filter(Boolean)}
                    />
                </div>
            </HeaderPortal>

            <GenericAppLayout
                headerSelector="#header"
                contentType="default"
                content={children}
                splitPanelOpen
                breadcrumbs={renderBreadcrumbs()}
                notifications={<Notifications />}
                navigation={
                    <SideNavigation
                        header={{ href: '#', text: t('common.control_plane') }}
                        activeHref={activeHref}
                        items={navLinks}
                        onFollow={onFollowHandler}
                    />
                }
                tools={
                    <>
                        <Tabs
                            activeTabId={toolsActiveTab}
                            onChange={(event) => onChangeToolsTab(event.detail.activeTabId as ToolsTabs)}
                            tabs={[
                                isVisibleInfoTab && {
                                    id: ToolsTabs.INFO,
                                    label: t('common.info'),
                                    content: (
                                        <HelpPanel header={helpPanelContent.header} footer={helpPanelContent.footer}>
                                            {helpPanelContent.body}
                                        </HelpPanel>
                                    ),
                                },
                                process.env.UI_VERSION === 'sky' && {
                                    id: ToolsTabs.TUTORIAL,
                                    label: t('common.tutorial_other'),
                                    content: (
                                        <TutorialPanel
                                            onFeedbackClick={() =>
                                                window.prompt('Please enter your feedback here (this will not be saved):')
                                            }
                                        />
                                    ),
                                },
                            ].filter(Boolean)}
                        />
                    </>
                }
                toolsHide={!toolsIsOpen}
                toolsOpen={toolsIsOpen}
                toolsWidth={330}
                onToolsChange={onChangeToolHandler}
            />

            <TallyComponent />
        </AnnotationContext>
    );
};

export default AppLayout;
