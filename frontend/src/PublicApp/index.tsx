import React from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import enMessages from '@cloudscape-design/components/i18n/messages/all.en.json';
import { applyMode, Mode } from '@cloudscape-design/global-styles';

import { AppLayout, BreadcrumbGroup, BreadcrumbGroupProps, Button, I18nProvider, TopNavigation } from 'components';
import { DarkThemeIcon, LightThemeIcon } from 'layouts/AppLayout/themeIcons';

import { DISCORD_URL } from 'consts';
import { useAppDispatch, useAppSelector } from 'hooks';
import { goToUrl } from 'libs';
import { ROUTES } from 'routes';

import { selectBreadcrumbs, selectSystemMode, setSystemMode } from 'App/slice';

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

const askAi = () => {
    window.document.body.focus();
    window?.Kapa?.open();
};

const HeaderPortal = ({ children }: PortalProps) => {
    const domNode = document.querySelector('#header');
    if (domNode) return createPortal(children, domNode);
    return null;
};

export const PublicApp: React.FC<React.PropsWithChildren> = ({ children }) => {
    const isSky = process.env.UI_VERSION === 'sky';
    const { t } = useTranslation();
    const dispatch = useAppDispatch();
    const navigate = useNavigate();
    const { pathname } = useLocation();
    const breadcrumbs = useAppSelector(selectBreadcrumbs);
    const isAuth = pathname === ROUTES.AUTH.LOGIN || pathname === ROUTES.AUTH.TOKEN;
    const onFollow: BreadcrumbGroupProps['onFollow'] = (event) => {
        event.preventDefault();
        navigate(event.detail.href);
    };
    const systemMode = useAppSelector(selectSystemMode) ?? '';
    const ThemeIcon = THEME_ICON_MAP[systemMode];

    const onChangeSystemModeToggle = (event: { preventDefault: () => void }) => {
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
                <div
                    className={styles.header}
                    ref={(element) => {
                        if (element) applyMode(Mode.Dark, element);
                    }}
                >
                    <TopNavigation
                        className={styles.navigation}
                        i18nStrings={i18nStrings}
                        identity={{
                            href: ROUTES.BASE,
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
                    {isSky && !isAuth && (
                        <div className={styles.signIn}>
                            <Button
                                variant="normal"
                                href={ROUTES.AUTH.LOGIN}
                                onFollow={(event) => {
                                    event.preventDefault();
                                    navigate(ROUTES.AUTH.LOGIN);
                                }}
                            >
                                {t('common.login')}
                            </Button>
                        </div>
                    )}
                </div>
            </HeaderPortal>

            <I18nProvider locale="en" messages={[enMessages]}>
                <AppLayout
                    headerSelector="#header"
                    contentType="default"
                    disableContentPaddings={!isSky || isAuth || pathname === ROUTES.BASE}
                    navigationHide
                    toolsHide
                    content={children ?? <Outlet />}
                    breadcrumbs={
                        isSky && pathname.startsWith(ROUTES.PRESETS.LIST) && breadcrumbs ? (
                            <BreadcrumbGroup items={breadcrumbs} onFollow={onFollow} />
                        ) : undefined
                    }
                />
            </I18nProvider>
        </>
    );
};
