import React from 'react';
import { createPortal } from 'react-dom';
import { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AppLayout as GenericAppLayout, SideNavigation, TopNavigation } from 'components';
import { ROUTES } from 'routes';
import { useAppSelector } from 'hooks';
import { selectUserName } from 'App/slice';
import logo from 'assets/images/logo.svg';

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

    const userName = useAppSelector(selectUserName);

    const onFollowHandler: SideNavigationProps['onFollow'] = (event) => {
        event.preventDefault();
        navigate(event.detail.href);
    };

    const i18nStrings = {
        overflowMenuTriggerText: '',
        overflowMenuTitleText: '',
        overflowMenuBackIconAriaLabel: '',
        overflowMenuDismissIconAriaLabel: '',
    };

    const profileActions = [{ type: 'button', href: ROUTES.LOGOUT, id: 'signout', text: 'Sign out' }];

    return (
        <>
            <HeaderPortal>
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
            </HeaderPortal>

            <GenericAppLayout
                headerSelector="#header"
                content={children}
                splitPanelOpen
                toolsHide
                navigation={
                    <SideNavigation
                        activeHref={pathname}
                        items={[
                            { type: 'link', text: t('navigation.hubs'), href: ROUTES.HUB.LIST },
                            { type: 'link', text: t('navigation.members'), href: ROUTES.MEMBER.LIST },
                        ]}
                        onFollow={onFollowHandler}
                    />
                }
            />
        </>
    );
};

export default AppLayout;
