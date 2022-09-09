import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as routes from 'routes';
import { ReactComponent as Logo } from 'assets/images/logo.svg';
import cn from 'classnames';
import Button from 'components/Button';
import { ReactComponent as MenuCloseIcon } from 'assets/icons/menu-close.svg';
import { ReactComponent as MenuIcon } from 'assets/icons/menu.svg';
import css from './index.module.css';
import {ReactComponent as GithubCircleIcon} from "../../../../assets/icons/github-circle.svg";
import {goToUrl} from "../../../../libs";

const Header: React.FC = () => {
    const navigate = useNavigate();
    const [showMenu, setShowMenu] = useState<boolean>(false);
    const toggleMenu = () => setShowMenu((val) => !val);

    /*const toSignIn = () => {
        navigate(routes.login());
    };

    const toSignUp = () => {
        navigate(routes.signUp());
    };*/

    const goToDownload = () => {
        goToUrl('https://docs.dstack.ai/installation', true);
    };

    const goToGithub = () => {
        goToUrl('https://github.com/dstackai/dstack', true);
    };

    return (
        <header className={css.header}>
            <div className={css.container}>
                <Link className={css.logo} to={routes.main()}>
                    <Logo width={150} height={33} />
                </Link>

                <menu className={cn(css.menu, { [css.show]: showMenu })}>
                    <Button
                        displayAsRound
                        className={css.close}
                        dimension="l"
                        appearance="black-transparent"
                        onClick={toggleMenu}
                        icon={<MenuCloseIcon />}
                    />

                    <div className={css.links}>
                        {/*<a href={'https://github.com/dstackai/dstack'} target={'_blank'} className={css.link}>
                            GitHub
                        </a>*/}

                        <a href={'https://docs.dstack.ai'} target={'_blank'} className={css.link}>
                            Docs
                        </a>

                        {/*<a href={'https://blog.dstack.ai'} target={'_blank'} className={css.link}>
                            Blog
                        </a>*/}

                        {/*<a
                                href={'https://dstackai.jobspage.co'}
                                target={'_blank'}
                                className={css.link}
                            >
                                Careers
                            </a>*/}

                        <div className={cn(css.headerButton, css.ctaButton)}>
                            <Button type="button" appearance="black-stroke" dimension="l" className={css.button} onClick={goToGithub}>
                                <GithubCircleIcon className={css.gitHubIcon} /> GitHub
                            </Button>
                        </div>

                        <div className={cn(css.headerButton, css.ctaButton)}>
                            <Button type="button" appearance="black-fill" dimension="l" className={css.button} onClick={goToDownload}>
                                Download
                            </Button>
                        </div>

                        {/*<div className={cn(css.headerButton, css.signInButton)}>
                            <Button onClick={toSignIn} appearance="gray-stroke" dimension="l">
                                Login
                            </Button>
                        </div>*/}

                        {/*<div className={cn(css.headerButton, css.signUpButton)}>
                            <Button onClick={toSignUp} appearance="blue-fill" dimension="l">
                                Sign up
                            </Button>
                        </div>*/}
                    </div>
                </menu>

                <Button
                    displayAsRound
                    className={css.menuButton}
                    dimension="l"
                    appearance="black-transparent"
                    onClick={toggleMenu}
                    icon={<MenuIcon />}
                />
            </div>
        </header>
    );
};

export default Header;
