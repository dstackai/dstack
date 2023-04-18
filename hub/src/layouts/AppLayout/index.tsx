import React from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { SideNavigationProps } from '@cloudscape-design/components/side-navigation';

import { AppLayout as GenericAppLayout, BreadcrumbGroup, Notifications, SideNavigation, TopNavigation } from 'components';

import { useAppSelector } from 'hooks';
import { ROUTES } from 'routes';

import { selectBreadcrumbs, selectUserName } from 'App/slice';

import logo from 'assets/images/logo.svg';
import styles from './index.module.scss';

type PortalProps = { children: React.ReactNode };
const HeaderPortal = ({ children }: PortalProps) => {
    const domNode = document.querySelector('#header');
    if (domNode) return createPortal(children, domNode);
    return null;
};
const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { pathname } = useLocation();
    const activeHref = '/' + pathname.split('/')[1];

    const userName = useAppSelector(selectUserName) ?? '';
    const breadcrumbs = useAppSelector(selectBreadcrumbs);

    const onFollowHandler: SideNavigationProps['onFollow'] = (event) => {
        event.preventDefault();
        navigate(event.detail.href);
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
        { type: 'button', href: ROUTES.USER.DETAILS.FORMAT(userName), id: 'profile', text: t('common.profile') },
        { type: 'button', href: ROUTES.LOGOUT, id: 'signout', text: t('common.sign_out') },
    ];

    return (
        <>
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
                                type: 'menu-dropdown',
                                text: userName,
                                iconName: 'user-profile',
                                items: profileActions,
                                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                                // @ts-ignore
                                onItemFollow: onFollowHandler,
                            },
                        ]}
                    />
                </div>
            </HeaderPortal>

            <GenericAppLayout
                headerSelector="#header"
                content={children}
                splitPanelOpen
                toolsHide
                breadcrumbs={renderBreadcrumbs()}
                notifications={<Notifications />}
                navigation={
                    <SideNavigation
                        // header={{
                        //     text: t('navigation.settings'),
                        //     href: ROUTES.BASE,
                        // }}
                        activeHref={activeHref}
                        items={[
                            {
                                type: 'section-group',
                                title: t('navigation.settings'),
                                items: [
                                    { type: 'link', text: t('navigation.projects'), href: ROUTES.PROJECT.LIST },
                                    { type: 'link', text: t('navigation.users'), href: ROUTES.USER.LIST },
                                ],
                            },
                        ]}
                        onFollow={onFollowHandler}
                    />
                }
            />
        </>
    );
};

export default AppLayout;
