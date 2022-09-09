import React from 'react';
import cn from 'classnames';
import { ReactComponent as Logo } from 'assets/images/logo.svg';
import { ReactComponent as FooterLogo } from 'assets/images/landing-footer-logo.svg';
import { ReactComponent as LikedInIcon } from 'assets/icons/linkedin.svg';
import { ReactComponent as TwitterIcon } from 'assets/icons/twitter.svg';
import { ReactComponent as SubstackIcon } from 'assets/icons/substack.svg';
import { ReactComponent as SlackIcon } from 'assets/icons/slack.svg';
import { ReactComponent as GithubCircleIcon } from 'assets/icons/github-circle.svg';
import css from './index.module.css';

export type Props = React.HTMLAttributes<HTMLDivElement>;

const Footer: React.FC<Props> = ({ className, ...props }) => {
    const openChat = (event: React.MouseEvent<HTMLAnchorElement>) => {
        event.preventDefault();
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        window.$crisp.push(['do', 'chat:show']);
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        window.$crisp.push(['do', 'chat:open']);
    };

    return (
        <footer className={cn(css.footer, className)} {...props}>
            <div className={css.container}>
                <div className={css.footerLogoCopyright}>
                    <Logo height={50} width={100} />

                    <div className={css.copyright}>© 2022 dstack GmbH</div>

                    <menu className={css.footerMenu}>
                        <ul className={css.footerSocialList}>
                            <li className={css.footerSocialItem}>
                                <a href="https://github.com/dstackai/dstack" target="_blank">
                                    <GithubCircleIcon />
                                </a>
                            </li>
                            <li className={css.footerSocialItem}>
                                <a
                                    href="https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ/"
                                    target="_blank"
                                >
                                    <SlackIcon />
                                </a>
                            </li>
                            <li className={css.footerSocialItem}>
                                <a href="https://twitter.com/dstackai" target="_blank">
                                    <TwitterIcon />
                                </a>
                            </li>
                            <li className={css.footerSocialItem}>
                                <a href="https://www.linkedin.com/company/dstackai" target="_blank">
                                    <LikedInIcon />
                                </a>
                            </li>
                        </ul>
                    </menu>
                </div>

                <div className={css.footerMenus}>
                    <menu className={css.footerMenu}>
                        <div className={css.footerMenuTitle}>Docs</div>

                        <ul className={css.footerMenuList}>
                            <li className={css.footerMenuItem}>
                                <a href="https://docs.dstack.ai/" target="_blank">
                                    Intro
                                </a>
                            </li>
                            <li className={css.footerMenuItem}>
                                <a href="https://docs.dstack.ai/concepts" target="_blank">
                                    Concepts
                                </a>
                            </li>
                            <li className={css.footerMenuItem}>
                                <a href="https://docs.dstack.ai/quickstat" target="_blank">
                                    Quickstart
                                </a>
                            </li>
                        </ul>
                    </menu>

                    <menu className={css.footerMenu}>
                        <div className={css.footerMenuTitle}>GitHub</div>

                        <ul className={css.footerMenuList}>
                            <li className={css.footerMenuItem}>
                                <a href="https://github.com/dstackai/dstack" target="_blank">
                                    Code
                                </a>
                            </li>

                            <li className={css.footerMenuItem}>
                                <a href="https://github.com/dstackai/dstack/issues" target="_blank">
                                    Issues
                                </a>
                            </li>
                        </ul>
                    </menu>

                    <menu className={css.footerMenu}>
                        <div className={css.footerMenuTitle}>Community</div>

                        <ul className={css.footerMenuList}>
                            <li className={css.footerMenuItem}>
                                <a href="https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ">
                                    Slack chat
                                </a>
                            </li>

                            <li className={css.footerMenuItem}>
                                <a href="https://dstack.us7.list-manage.com/subscribe/post?u=265ccb1949b39a23d350b177f&id=8cfbe50714&f_id=0034c4e4f0">
                                    Mailing list
                                </a>
                            </li>

                            {/*<li className={css.footerMenuItem}>*/}
                            {/*    <a href="#" onClick={openChat}>*/}
                            {/*        Open a chat*/}
                            {/*    </a>*/}
                            {/*</li>*/}
                        </ul>
                    </menu>

                    {/*<menu className={css.footerMenu}>*/}
                        {/*<div className={css.footerMenuTitle}>Follow us</div>*/}

                        {/*<ul className={css.footerMenuList}>*/}
                            {/*<li className={cn(css.footerMenuItem, css.githubWidget)}>*/}
                            {/*    <iframe*/}
                            {/*        src="https://ghbtns.com/github-btn.html?user=dstackai&repo=dstack&type=star&count=true"*/}
                            {/*        frameBorder="0"*/}
                            {/*        scrolling="0"*/}
                            {/*        width="100"*/}
                            {/*        height="20"*/}
                            {/*        title="GitHub"*/}
                            {/*    />*/}

                            {/*    <GitHubButton*/}
                            {/*        href="https://github.com/dstackai/dstack"*/}
                            {/*        // data-color-scheme="no-preference: light_high_contrast; light: light_high_contrast; dark: light_high_contrast;"*/}
                            {/*        data-size="small"*/}
                            {/*        data-show-count="true"*/}
                            {/*        aria-label="Star dstackai/dstack on GitHub"*/}
                            {/*    >*/}
                            {/*        Star*/}
                            {/*    </GitHubButton>*/}
                            {/*</li>*/}

                            {/*<li className={css.footerMenuItem}>
                                <a href="https://twitter.com/dstackai" target="_blank">
                                    Twitter
                                </a>
                            </li>

                            <li className={css.footerMenuItem}>
                                <a href={'https://www.linkedin.com/company/dstackai'} target={'_blank'} className={css.link}>
                                    LinkedIn
                                </a>
                            </li>*/}

                            {/*<li className={css.footerMenuItem}>
                                <a href="https://mlopsfluff.dstack.ai/">MLOps Fluff</a>
                            </li>*/}
                        {/*</ul>*/}
                    {/*</menu>*/}

                    <menu className={css.footerMenu}>
                        <div className={css.footerMenuTitle}>Company</div>

                        <ul className={css.footerMenuList}>
                            {/*<li className={css.footerMenuItem}>
                                <a href="https://blog.dstack.ai/">Blog</a>
                            </li>*/}

                            <li className={css.footerMenuItem}>
                                <a
                                    href="https://dstackai.notion.site/dstack-ai-Privacy-Policy-1dc143f6e52147228441cc4e2100cd78"
                                    target="_blank"
                                >
                                    Privacy
                                </a>
                            </li>
                        </ul>
                    </menu>
                </div>
            </div>
        </footer>
    );
};

export default Footer;
