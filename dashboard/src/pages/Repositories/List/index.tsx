import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';
import { useGetRepositoriesQuery } from 'services/repositories';
import { Link, useParams } from 'react-router-dom';
import EmptyRepositoryList from './components/Empty';
import { ReactComponent as LockIcon } from 'assets/icons/lock.svg';
import { ReactComponent as EarthIcon } from 'assets/icons/earth.svg';
import { ReactComponent as TagIcon } from 'assets/icons/tag-outline.svg';
import { ReactComponent as ClockIcon } from 'assets/icons/clock.svg';
import { getDateAgoSting } from 'libs';
import css from './index.module.css';
import { getRouterModule, RouterModules } from 'route';
import { URL_PARAMS } from 'route/url-params';

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    userName?: string;
}

const Public: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className, ...props }) => {
    const { t } = useTranslation();

    return (
        <div className={cn(css.privacy, className)} {...props}>
            <EarthIcon /> {t('public')}
        </div>
    );
};

const Private: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className, ...props }) => {
    const { t } = useTranslation();

    return (
        <div className={cn(css.privacy, className)} {...props}>
            <LockIcon />
            {t('private')}
        </div>
    );
};

const getRepoName = (repo: IRepository, userName: string) => {
    if (userName === repo.repo_user_name) return repo.repo_name;

    return `${repo.repo_user_name}/${repo.repo_name}`;
};

const ListItem: React.FC<IRepository & { userName: string }> = ({ userName, ...repo }) => {
    const { t } = useTranslation();
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);
    const repoName = getRepoName(repo, userName);

    const repoLink = useMemo<string>(() => {
        const pathName = ['app', userName === repo.repo_user_name ? 'user-repo' : 'user-repouser-repo'].join('.');

        return newRouter.buildUrl(pathName, {
            [URL_PARAMS.USER_NAME]: userName,
            [URL_PARAMS.REPO_USER_NAME]: repo.repo_user_name,
            [URL_PARAMS.REPO_NAME]: repo.repo_name,
        });
    }, [userName, repo]);

    return (
        <Link to={repoLink} className={css.card}>
            <div className={cn(css.name, 'mono-font')}>{repoName}</div>
            {repo.visibility === 'private' && <Private />}
            {repo.visibility === 'public' && <Public />}

            <div className={css.additions}>
                {repo.last_run_at && (
                    <li className={css.addition}>
                        <ClockIcon />
                        {t('last_run')} {getDateAgoSting(repo.last_run_at)}
                    </li>
                )}

                {!!repo.tags_count && (
                    <li className={css.addition}>
                        <TagIcon />
                        {t('tagWithCount', { count: repo.tags_count })}
                    </li>
                )}
            </div>
        </Link>
    );
};

const RepositoryList: React.FC<Props> = ({ userName: userNameProp, className, ...props }) => {
    const { userName: userNameUrlParam } = useParams();
    const userName = userNameProp ?? userNameUrlParam ?? '';

    const { data, isLoading } = useGetRepositoriesQuery(
        { user_name: userName },
        { skip: process.env.HOST ? false : !userName },
    );

    if (isLoading || !data)
        return (
            <div className={cn(css.list, className)} {...props}>
                <div className="skeleton-element" />
                <div className="skeleton-element" />
                <div className="skeleton-element" />
                <div className="skeleton-element" />
            </div>
        );

    if (!data.length) return <EmptyRepositoryList />;

    return (
        <div className={cn(css.list, className)} {...props}>
            {data.map((r, index) => (
                <ListItem key={index} {...r} userName={userName} />
            ))}
        </div>
    );
};

export default RepositoryList;
