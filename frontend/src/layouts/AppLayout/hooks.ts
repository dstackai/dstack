import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useMatch } from 'react-router-dom';

import { SideNavigationProps } from 'components';

import { DISCORD_URL, DOCS_URL } from 'consts';
import { useAppSelector, usePermissionGuard } from 'hooks';
import { goToUrl } from 'libs';
import { ROUTES } from 'routes';
import { useGetServerInfoQuery } from 'services/server';
import { GlobalUserRole } from 'types';

import { selectUserName } from 'App/slice';

export const useSideNavigation = () => {
    const { t } = useTranslation();
    const userName = useAppSelector(selectUserName) ?? '';
    const { pathname } = useLocation();
    const [isGlobalAdmin] = usePermissionGuard({ allowedGlobalRoles: [GlobalUserRole.ADMIN] });
    const { data: serverInfoData } = useGetServerInfoQuery();

    const isPoolDetails = Boolean(useMatch(ROUTES.FLEETS.DETAILS.TEMPLATE));
    const billingUrl = ROUTES.USER.BILLING.LIST.FORMAT(userName);
    const userProjectsUrl = ROUTES.USER.PROJECTS.FORMAT(userName);

    const generalLinks = [
        { type: 'link', text: t('navigation.runs'), href: ROUTES.RUNS.LIST },
        { type: 'link', text: t('navigation.models'), href: ROUTES.MODELS.LIST },
        { type: 'link', text: t('navigation.fleets'), href: ROUTES.FLEETS.LIST },
        { type: 'link', text: t('navigation.instances'), href: ROUTES.INSTANCES.LIST },
        { type: 'link', text: t('navigation.volumes'), href: ROUTES.VOLUMES.LIST },
        { type: 'link', text: t('navigation.project_other'), href: ROUTES.PROJECT.LIST },

        isGlobalAdmin && {
            type: 'link',
            text: t('navigation.users'),
            href: ROUTES.USER.LIST,
        },
    ].filter(Boolean);

    const userSettingsLinks = [
        {
            type: 'link',
            text: t('navigation.settings'),
            href: ROUTES.USER.DETAILS.FORMAT(userName),
        },
        process.env.UI_VERSION === 'sky' && {
            type: 'link',
            text: t('navigation.billing'),
            href: billingUrl,
        },
        {
            type: 'link',
            text: t('users.projects'),
            href: userProjectsUrl,
        },
    ].filter(Boolean);

    const navLinks: SideNavigationProps['items'] = [
        {
            type: 'section-group',
            title: t('navigation.general'),
            items: generalLinks,
        },

        { type: 'divider' },

        {
            type: 'section-group',
            title: t('navigation.account'),
            items: userSettingsLinks,
        },

        { type: 'divider' },

        {
            type: 'section-group',
            title: t('navigation.resources'),
            items: [
                {
                    type: 'link',
                    text: t('common.docs'),
                    external: true,
                    href: DOCS_URL,
                    // onClick: () => goToUrl(DOCS_URL, true),
                },
                {
                    type: 'link',
                    text: t('common.discord'),
                    external: true,
                    href: DISCORD_URL,
                    onClick: () => goToUrl(DISCORD_URL, true),
                },
            ],
        },

        { type: 'divider' },

        {
            type: 'link',
            href: '#version',
            text: `dstack version: ${serverInfoData?.server_version ?? 'No version'}`,
        },
    ].filter(Boolean) as SideNavigationProps['items'];

    const activeHref = useMemo(() => {
        if (isPoolDetails) {
            return ROUTES.FLEETS.LIST;
        }

        const generalActiveLink = generalLinks.find((linkItem) => pathname.indexOf(linkItem.href) === 0);

        if (generalActiveLink) return pathname;

        const settingsActiveLink = userSettingsLinks.find((linkItem) => linkItem.href === pathname);

        if (settingsActiveLink) return pathname;

        return '/' + pathname.split('/')[1];
    }, [pathname, userName]);

    return { navLinks, activeHref, billingUrl } as const;
};
