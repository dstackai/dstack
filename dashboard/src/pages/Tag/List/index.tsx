import React from 'react';
import { useGetTagsQuery } from 'services/tags';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import EmptyMessage from 'components/EmptyMessage';
import TagCard from './components/TagCard';
import { useAppProgress } from 'hooks';
import css from './style.module.css';

const TagList: React.FC = () => {
    const { t } = useTranslation();
    const { repoUserName, repoName } = useParams();

    const {
        data: tags,
        isLoading,
        isFetching,
    } = useGetTagsQuery({
        repoUserName: repoUserName ?? '',
        repoName: repoName ?? '',
    });

    useAppProgress(isFetching);

    return (
        <section className={css.list}>
            {isLoading && (
                <div className={css.grid}>
                    <div className="skeleton-element" />
                    <div className="skeleton-element" />
                    <div className="skeleton-element" />
                    <div className="skeleton-element" />
                </div>
            )}

            {!tags?.length && !isLoading && (
                <EmptyMessage
                    className={css.emptyMessage}
                    title={t('it_is_pretty_empty')}
                    description={t('you_do_not_have_any_tags_yet')}
                />
            )}

            {!isLoading && !!tags?.length && (
                <div className={css.grid}>
                    {tags.map((row, index) => (
                        <TagCard key={index} tag={row} />
                    ))}
                </div>
            )}
        </section>
    );
};

export default TagList;
