import React from 'react';
import cn from 'classnames';
import { NavLink, NavLinkProps } from 'react-router-dom';
import css from './index.module.css';

export type Props = React.HTMLAttributes<HTMLDivElement>;

const Tabs: React.FC<Props> = ({ className, children, ...props }) => {
    return (
        <div className={cn(css.tabs, className)} {...props}>
            {children}
        </div>
    );
};

export type TabItemNavLinkProps = NavLinkProps;

const TabItemNavLink: React.FC<TabItemNavLinkProps> = ({ className, children, ...props }) => {
    return (
        <NavLink className={({ isActive }) => cn(css.tab, className, { active: isActive })} {...props}>
            {children}
        </NavLink>
    );
};

export interface TabItemProps extends React.HTMLAttributes<HTMLDivElement> {
    active?: boolean;
}

const TabItem: React.FC<TabItemProps> = ({ className, active, children, ...props }) => {
    return (
        <div className={cn(css.tab, className, { active })} {...props}>
            {children}
        </div>
    );
};

export default Object.assign(Tabs, {
    TabItemNavLink,
    TabItem,
});
