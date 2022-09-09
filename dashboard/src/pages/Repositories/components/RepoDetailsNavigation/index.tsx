import React, { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Tabs, { Props as TabsProps } from 'components/Tabs';
import { getRouterModule, RouterModules } from 'route';
import { URL_PARAMS } from 'route/url-params';

export type Props = TabsProps;

const RepoDetailsNavigation: React.FC<Props> = (props) => {
    const { t } = useTranslation();
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);
    const urlParams = useParams();

    const repoLink = useMemo<string>(() => {
        const pathName = ['app', urlParams[URL_PARAMS.REPO_USER_NAME] ? 'user-repouser-repo' : 'user-repo', 'repo']
            .filter(Boolean)
            .join('.');

        return newRouter.buildUrl(pathName, {
            [URL_PARAMS.USER_NAME]: urlParams[URL_PARAMS.USER_NAME],
            [URL_PARAMS.REPO_USER_NAME]: urlParams[URL_PARAMS.REPO_USER_NAME],
            [URL_PARAMS.REPO_NAME]: urlParams[URL_PARAMS.REPO_NAME],
        });
    }, [urlParams]);

    const tagsLink = useMemo<string>(() => {
        const pathName = ['app', urlParams[URL_PARAMS.REPO_USER_NAME] ? 'user-repouser-repo' : 'user-repo', 'repo', 'tag']
            .filter(Boolean)
            .join('.');

        return newRouter.buildUrl(pathName, {
            [URL_PARAMS.USER_NAME]: urlParams[URL_PARAMS.USER_NAME],
            [URL_PARAMS.REPO_USER_NAME]: urlParams[URL_PARAMS.REPO_USER_NAME],
            [URL_PARAMS.REPO_NAME]: urlParams[URL_PARAMS.REPO_NAME],
        });
    }, [urlParams]);

    return (
        <Tabs {...props}>
            <Tabs.TabItemNavLink end to={repoLink}>
                {t('run_other')}
            </Tabs.TabItemNavLink>
            <Tabs.TabItemNavLink to={tagsLink}>{t('tag_other')}</Tabs.TabItemNavLink>
        </Tabs>
    );
};

export default RepoDetailsNavigation;
