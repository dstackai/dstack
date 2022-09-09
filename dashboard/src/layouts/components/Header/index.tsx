import React from 'react';
import cn from 'classnames';
import { Link } from 'react-router-dom';
import { ReactComponent as Logo } from 'assets/images/logo.svg';
import css from './index.module.css';

export interface Props {
    logoLink?: string;
    children?: React.ReactNode;
    className?: string;
}

const Header: React.FC<Props> = ({ className, logoLink = '/', children }) => {
    return (
        <header className={cn(css.header, className)}>
            <Link className={css.logo} to={logoLink}>
                <Logo />
            </Link>

            {children}
        </header>
    );
};

export default Header;
