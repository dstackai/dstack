import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useMatch, useNavigate, useParams } from 'react-router-dom';

import { ButtonDropdownProps, SideNavigationProps } from 'components';

import { useAppSelector, usePermissionGuard } from 'hooks';
import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { ROUTES } from 'routes';
import { useGetProjectsQuery } from 'services/project';
import { GlobalUserRole } from 'types';

import { selectUserName } from 'App/slice';
import { useCheckAvailableProjectPermission } from 'pages/Project/hooks/useCheckAvailableProjectPermission';

export const useSideNavigation = () => {
    const { t } = useTranslation();
    const userName = useAppSelector(selectUserName) ?? '';
    const { pathname } = useLocation();
    const { selectedProject } = useProjectDropdown();
    const [isAvailableAdministrationLinks] = usePermissionGuard({ allowedGlobalRoles: [GlobalUserRole.ADMIN] });

    const isPoolDetails = Boolean(useMatch(ROUTES.FLEETS.DETAILS.TEMPLATE));

    const mainProjectSettingsUrl = selectedProject ? ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(selectedProject) : null;
    const billingUrl = ROUTES.USER.BILLING.LIST.FORMAT(userName);

    const projectLinks = [
        { type: 'link', text: t('navigation.runs'), href: ROUTES.RUNS.LIST },
        { type: 'link', text: t('navigation.fleets'), href: ROUTES.FLEETS.LIST },
        { type: 'link', text: t('navigation.models'), href: ROUTES.MODELS.LIST },

        mainProjectSettingsUrl && {
            type: 'link',
            text: t('navigation.settings'),
            href: mainProjectSettingsUrl,
        },
    ].filter(Boolean);

    const administrationLinks = [
        { type: 'link', text: t('navigation.runs'), href: ROUTES.ADMINISTRATION.RUNS.LIST },
        { type: 'link', text: t('navigation.fleets'), href: ROUTES.ADMINISTRATION.FLEETS.LIST },
        { type: 'link', text: t('navigation.project_other'), href: ROUTES.PROJECT.LIST },

        {
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
    ].filter(Boolean);

    const navLinks: SideNavigationProps['items'] = [
        {
            type: 'section',
            text: t('navigation.project'),
            items: projectLinks,
        },

        isAvailableAdministrationLinks && {
            type: 'section',
            text: t('navigation.administration'),
            items: administrationLinks,
        },

        {
            type: 'section',
            text: t('navigation.account'),
            items: userSettingsLinks,
        },
    ].filter(Boolean) as SideNavigationProps['items'];

    const activeHref = useMemo(() => {
        if (isPoolDetails) {
            return ROUTES.FLEETS.LIST;
        }

        const administrationActiveLink = administrationLinks.find((linkItem) => linkItem.href === pathname);

        if (administrationActiveLink) return pathname;

        const settingsActiveLink = userSettingsLinks.find((linkItem) => linkItem.href === pathname);

        if (settingsActiveLink) return pathname;

        const projectActiveLink = projectLinks.find((linkItem) => {
            return pathname.indexOf(linkItem.href) === 0;
        });

        if (projectActiveLink) return projectActiveLink.href;

        return '/' + pathname.split('/')[1];
    }, [pathname, userName, selectedProject]);

    return { navLinks, activeHref, mainProjectSettingsUrl, billingUrl } as const;
};

export const useProjectDropdown = () => {
    const { t } = useTranslation();
    const { pathname } = useLocation();
    const navigate = useNavigate();
    const params = useParams();
    const paramProjectName = params.projectName;
    const { data } = useGetProjectsQuery();
    const [selectedProject, setSelectedProject] = useLocalStorageState('selected-project', data?.[0]?.project_name ?? null);
    const { isAvailableProjectManaging } = useCheckAvailableProjectPermission();

    const isAvailableProjectDropdown =
        ![ROUTES.PROJECT.LIST, ROUTES.ADMINISTRATION.RUNS.LIST].includes(pathname) && pathname.indexOf(ROUTES.USER.LIST) !== 0;
    const onFollowProject: ButtonDropdownProps['onItemFollow'] = (event) => {
        event.preventDefault();

        if (event.detail.href === ROUTES.PROJECT.ADD) {
            navigate(event.detail.href);
            return;
        }

        setSelectedProject(event.detail.href!);
    };

    useEffect(() => {
        if (paramProjectName && paramProjectName !== selectedProject) {
            setSelectedProject(paramProjectName);
        }
    }, [paramProjectName]);

    useEffect(() => {
        if (data?.length) {
            if (!selectedProject) {
                setSelectedProject(data[0].project_name);
            } else {
                const isProjectListHasSelected = data.some((p) => p.project_name === selectedProject);

                if (!isProjectListHasSelected) {
                    setSelectedProject(data[0].project_name);
                }
            }
        }
    }, [data, selectedProject]);

    const projectsDropdownList = useMemo<ButtonDropdownProps.ItemOrGroup[]>(() => {
        const items: ButtonDropdownProps.ItemOrGroup[] = [];

        if (data) {
            data.forEach((project) => {
                items.push({
                    text: project.project_name,
                    href: project.project_name,
                } as ButtonDropdownProps.ItemOrGroup);
            });
        }

        if (isAvailableProjectManaging) {
            const addButton: ButtonDropdownProps.ItemOrGroup = {
                text: t('common.create', { text: t('navigation.project') }),
                href: ROUTES.PROJECT.ADD,
                iconName: 'add-plus',
            };

            items.push(addButton);
        }

        return items;
    }, [data, isAvailableProjectManaging]);

    return { projectsDropdownList, selectedProject, isAvailableProjectDropdown, onFollowProject } as const;
};
