import React from 'react';
import { Outlet } from 'react-router-dom';
import Header from 'layouts/components/Header';
import css from './index.module.css';
import Notifications from 'features/Notifications';
import { getRouterModule, RouterModules } from 'route';

interface Props {
    children?: React.ReactNode;
}

const AuthLayout: React.FC<Props> = ({ children }) => {
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);

    return (
        <div className={css.layout}>
            <Header className={css.header} logoLink={newRouter.buildUrl('app')} />
            <Notifications className={css.notifications} />

            <main className={css.content}>
                <Outlet />
                {children}
            </main>
        </div>
    );
};

export default AuthLayout;
