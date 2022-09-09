import React from 'react';
import PageTitle from 'components/PageTitle';
import { useTranslation } from 'react-i18next';
import { Outlet } from 'react-router-dom';
import Tabs from 'components/Tabs';
import css from './index.module.css';
import { getRouterModule, RouterModules } from 'route';

const Settings: React.FC = () => {
    const { t } = useTranslation();
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);

    return (
        <section className={css.settings}>
            <PageTitle>{t('settings')}</PageTitle>

            <Tabs className={css.tabs}>
                {!process.env.HOST && (
                    <>
                        <Tabs.TabItemNavLink to={newRouter.buildUrl('app.settings.account')}>
                            {t('account')}
                        </Tabs.TabItemNavLink>
                        <Tabs.TabItemNavLink to={newRouter.buildUrl('app.settings.git')}>{t('git')}</Tabs.TabItemNavLink>
                        <Tabs.TabItemNavLink to={newRouter.buildUrl('app.settings.clouds')}>
                            {t('cloud_other')}
                        </Tabs.TabItemNavLink>
                    </>
                )}

                <Tabs.TabItemNavLink to={newRouter.buildUrl('app.settings.secrets')}>{t('secret_other')}</Tabs.TabItemNavLink>
            </Tabs>

            <div className={css.content}>
                <Outlet />
            </div>
        </section>
    );
};

export default Settings;
