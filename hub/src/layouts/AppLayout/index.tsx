import React from 'react';
import { SideNavigationProps } from '@cloudscape-design/components/side-navigation';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ROUTES } from 'routes';
import { AppLayout as GenericAppLayout, SideNavigation } from 'components';

const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { pathname } = useLocation();

    const onFollowHandler: SideNavigationProps['onFollow'] = (event) => {
        event.preventDefault();
        navigate(event.detail.href);
    };

    return (
        <GenericAppLayout
            content={children}
            splitPanelOpen
            toolsHide
            navigation={
                <SideNavigation
                    activeHref={pathname}
                    header={{ href: ROUTES.BASE, text: t('navigation.dstack') ?? '' }}
                    items={[
                        { type: 'link', text: t('navigation.hubs'), href: ROUTES.HUB.LIST },
                        { type: 'link', text: t('navigation.users'), href: ROUTES.USER.LIST },
                    ]}
                    onFollow={onFollowHandler}
                />
            }
        />
    );
};

export default AppLayout;
