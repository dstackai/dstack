import React from 'react';
import { createPortal } from 'react-dom';
import { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AppLayout as GenericAppLayout, SideNavigation, TopNavigation, BreadcrumbGroup } from 'components';
import { ROUTES } from 'routes';
import { useAppSelector } from 'hooks';
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

    const userName = useAppSelector(selectUserName);
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

    const profileActions = [{ type: 'button', href: ROUTES.LOGOUT, id: 'signout', text: t('common.sign_out') }];

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
                                description: userName,
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
                navigation={
                    <SideNavigation
                        activeHref={activeHref}
                        items={[
                            { type: 'link', text: t('navigation.hubs'), href: ROUTES.HUB.LIST },
                            { type: 'link', text: t('navigation.users'), href: ROUTES.USER.LIST },
                        ]}
                        onFollow={onFollowHandler}
                    />
                }
            />
        </>
    );
};

export default AppLayout;
