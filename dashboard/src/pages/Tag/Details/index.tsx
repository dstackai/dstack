import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';
import { useNavigate, useParams } from 'react-router-dom';
import { URL_PARAMS } from 'route/url-params';
import BreadCrumbs from 'components/BreadCrumbs';
import Button from 'components/Button';
import { useAppProgress } from 'hooks';
import { ReactComponent as RefreshIcon } from 'assets/icons/refresh.svg';
import { getRouterModule, RouterModules } from 'route';
import { useDeleteMutation, useGetTagQuery, useRefetchTagMutation } from 'services/tags';
import { ReactComponent as DeleteOutlineIcon } from 'assets/icons/delete-outline.svg';
import RepoDetailsNavigation from '../../Repositories/components/RepoDetailsNavigation';
import EmptyMessage from 'components/EmptyMessage';
import ConfirmModal from 'components/ConfirmModal';
import Artifacts from 'features/Artifacts';
import Sidebar from 'components/details/DetailsSidebar';
import { getDateAgoSting } from 'libs';
import css from './index.module.css';

const TagDetails: React.FC = () => {
    const { t } = useTranslation();
    const [showConfirmDelete, setShowConfirmDelete] = useState<boolean>(false);
    const urlParams = useParams();
    const { repoUserName, repoName, tagName } = urlParams;
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);
    const navigate = useNavigate();

    const { data: tag, isLoading: isLoadingTag } = useGetTagQuery({
        repoUserName: repoUserName || '',
        repoName: repoName || '',
        tagName: tagName || '',
    });

    useAppProgress(isLoadingTag);
    const [deleteTag] = useDeleteMutation();
    const [refetchTag] = useRefetchTagMutation();

    const repoDetailsUrl = useMemo<string>(() => {
        const pathName = ['app', urlParams[URL_PARAMS.REPO_USER_NAME] ? 'user-repouser-repo' : 'user-repo', 'repo', 'tags']
            .filter(Boolean)
            .join('.');

        return newRouter.buildUrl(pathName, {
            [URL_PARAMS.USER_NAME]: urlParams[URL_PARAMS.USER_NAME],
            [URL_PARAMS.REPO_USER_NAME]: urlParams[URL_PARAMS.REPO_USER_NAME],
            [URL_PARAMS.REPO_NAME]: urlParams[URL_PARAMS.REPO_NAME],
        });
    }, [urlParams]);

    const refreshHandle = () => refetchTag({ tagName: tagName as string });

    const deleteTagHandle = () => {
        setShowConfirmDelete(true);
    };

    const confirmDeleteTag = () => {
        if (!tag?.tag_name) return;

        setShowConfirmDelete(false);

        deleteTag({
            repo_user_name: tag.repo_user_name,
            repo_name: tag.repo_name,
            tag_name: tag.tag_name,
        });

        navigate(repoDetailsUrl);
    };

    if (isLoadingTag) return null;

    return (
        <section className={css.details}>
            <div className={css.topSection}>
                <BreadCrumbs className={css.breadcrumbs}>
                    <BreadCrumbs.Item to={newRouter.buildUrl('app')}>{t('repository_other')}</BreadCrumbs.Item>
                    <BreadCrumbs.Item to={repoDetailsUrl}>{`${repoUserName}/${repoName}`}</BreadCrumbs.Item>
                </BreadCrumbs>

                <Button className={css.button} appearance="gray-stroke" icon={<RefreshIcon />} onClick={refreshHandle}>
                    {t('refresh')}
                </Button>
            </div>

            <RepoDetailsNavigation className={css.tabs} />

            {tag && (
                <div className={css.content}>
                    <div className={css.header}>
                        <h1 className={css.title}>{tag.tag_name}</h1>

                        <div className={css.buttons}>
                            <Button
                                appearance="gray-stroke"
                                displayAsRound
                                onClick={deleteTagHandle}
                                icon={<DeleteOutlineIcon />}
                            />
                        </div>
                    </div>

                    {!tag.artifacts?.length && (
                        <EmptyMessage
                            className={css.emptyMessage}
                            title={t('it_is_pretty_empty')}
                            description={t('you_do_not_have_any_artifacts')}
                        />
                    )}

                    {!!tag.artifacts?.length && (
                        <div className={css.artifactsWrapper}>
                            <div className={css.title}>{t('artifact_other')}</div>

                            <Artifacts
                                artifacts={tag.artifacts}
                                className={css.artifacts}
                                repo_user_name={tag.repo_user_name}
                                repo_name={tag.repo_name}
                            />
                        </div>
                    )}

                    <Sidebar className={css.sidebar}>
                        {tag && (
                            <>
                                <Sidebar.Property name={t('repository')}>
                                    <Sidebar.RepoAttrs
                                        repoUrl={`https://github.com/${repoUserName}/${repoName}`}
                                        hash={tag.repo_hash}
                                        branch={tag.repo_branch}
                                    />

                                    <a
                                        href={`https://github.com/${repoUserName}/${repoName}/commit/${tag.repo_hash}`}
                                        target="_blank"
                                    >
                                        {t('local_changes')}
                                    </a>
                                </Sidebar.Property>

                                <Sidebar.Property name={t('workflow')}>
                                    <span className={cn({ [css.gray]: !tag.workflow_name })}>
                                        {tag.workflow_name || t('no_name')}
                                    </span>
                                </Sidebar.Property>

                                <Sidebar.Property name={t('created')}>{getDateAgoSting(tag.created_at)}</Sidebar.Property>
                            </>
                        )}
                    </Sidebar>
                </div>
            )}

            <ConfirmModal
                title={t('delete')}
                confirmButtonProps={{ children: t('delete') }}
                ok={confirmDeleteTag}
                show={showConfirmDelete}
                close={() => setShowConfirmDelete(false)}
            >
                {t('confirm_messages.delete_tag')}
            </ConfirmModal>
        </section>
    );
};

export default TagDetails;
