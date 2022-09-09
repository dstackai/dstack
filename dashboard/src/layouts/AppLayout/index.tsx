import React from 'react';
import cn from 'classnames';
import { Outlet, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Header from 'layouts/components/Header';
import Dropdown from 'components/Dropdown';
import Avatar from 'components/Avatar';
import ProgressBar from 'components/ProgressBar';
import Notifications from 'features/Notifications';
import VariablesModal from 'features/VariablesModal';
import AppsModal from 'features/Run/AppsModal';
import ArtifactsModal from 'features/ArtifactsModal';
import { useGetUserInfoQuery } from 'services/user';
import { useAppDispatch, useAppSelector } from 'hooks';
import { clearAuthToken, selectAppProgress } from 'App/slice';
import css from './index.module.css';
import { getRouterModule, RouterModules } from 'route';
import { goToUrl } from 'libs';

const AppLayout: React.FC = () => {
    const { data: user } = useGetUserInfoQuery(undefined, { skip: process.env.HOST });
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);
    const progress = useAppSelector(selectAppProgress);
    const { t } = useTranslation();
    const dispatch = useAppDispatch();
    const navigate = useNavigate();

    const logOut = () => {
        location.pathname = newRouter.buildUrl('auth.login');
        dispatch(clearAuthToken());
    };

    const toSettings = () => navigate(newRouter.buildUrl('app.settings.account'));
    const toDocumentation = () => goToUrl('https://docs.dstack.ai/', true);

    const dropdownItems = [
        {
            children: t('settings'),
            onClick: toSettings,
        },
        {
            children: t('documentation'),
            onClick: toDocumentation,
        },
    ];

    if (!process.env.HOST)
        dropdownItems.push({
            children: t('log_out'),
            onClick: logOut,
        });

    return (
        <div className={css.layout}>
            <Header className={css.header} logoLink={newRouter.buildUrl('app')}>
                <Dropdown items={dropdownItems}>
                    <div className={cn(css.avatar, css.github)}>
                        <Avatar name={user?.user_name ?? 'host'} />
                    </div>
                </Dropdown>

                <ProgressBar isActive={progress.isActive} progress={progress.state} className={css.progress} />
            </Header>

            <Notifications className={css.notifications} />

            <main className={css.content}>
                <Outlet />
            </main>

            <AppsModal />
            <VariablesModal />
            <ArtifactsModal />
        </div>
    );
};

export default AppLayout;
