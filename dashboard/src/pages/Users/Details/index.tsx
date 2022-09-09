import cn from 'classnames';
import React from 'react';
import Avatar from 'components/Avatar';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useGetUserInfoQuery } from 'services/user';
import { useGetRepositoriesQuery } from 'services/repositories';
import { ReactComponent as GithubIcon } from 'assets/icons/github-circle.svg';
import RepositoryList from 'pages/Repositories/List';
import css from './index.module.css';

const UserDetails: React.FC = () => {
    const { t } = useTranslation();
    const { userName } = useParams();
    const { data, isLoading } = useGetUserInfoQuery(undefined, { skip: process.env.HOST });

    const { data: repoData, isLoading: isLoadingRepo } = useGetRepositoriesQuery(
        { user_name: userName },
        { skip: process.env.HOST ? false : !userName },
    );

    if (!process.env.HOST && (isLoading || !data || !repoData || isLoadingRepo)) return null;

    return (
        <section className={cn(css.details, { 'without-sidebar': process.env.HOST })}>
            {data && (
                <aside className={css.sidebar}>
                    <div className={css.userName}>{data.user_name}</div>
                    <Avatar className={css.avatar} name={data.user_name} appearance="square" size="xl" />

                    {data.github_user_name && (
                        <div className={css.link}>
                            <a
                                href={`https://github.com/${data.github_user_name}`}
                                title={`https://github.com/${data.github_user_name}`}
                            >
                                <GithubIcon width={14} height={14} />
                                {`https://github.com/${data.github_user_name}`}
                            </a>
                        </div>
                    )}

                    <ul className={css.points}>
                        <li className={css.point}>
                            {0} {t('app_other').toLowerCase()}
                        </li>
                    </ul>
                </aside>
            )}

            <div className={css.content}>
                <h1 className={css.title}>
                    {t('repository_other')} <span className={css.count}>{repoData?.length}</span>
                </h1>

                <RepositoryList userName={userName} />
            </div>
        </section>
    );
};

export default UserDetails;
