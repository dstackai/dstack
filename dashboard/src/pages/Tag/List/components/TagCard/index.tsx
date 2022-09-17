import React from 'react';
import cn from 'classnames';
import Button from 'components/Button';
import Dropdown from 'components/Dropdown';
import { ReactComponent as DotsIcon } from 'assets/icons/dots-vertical.svg';
import { ReactComponent as ClockIcon } from 'assets/icons/clock.svg';
import { getDateAgoSting, stopPropagation } from 'libs';
import { useTranslation } from 'react-i18next';
import { useDeleteMutation } from 'services/tags';
import { ReactComponent as LayersIcon } from 'assets/icons/layers.svg';
import { showArtifacts } from 'features/ArtifactsModal/slice';
import { artifactsToArtifactPaths } from 'libs/artifacts';
import { useAppDispatch } from 'hooks';
import css from './style.module.css';

export interface Props extends ITag {
    className?: string;
}

const TagCard: React.FC<Props> = ({ className, ...tag }) => {
    const { t } = useTranslation();
    const [deleteTag, { isLoading: isDeleting }] = useDeleteMutation();
    const dispatch = useAppDispatch();

    const deleteHandle = () => {
        deleteTag({
            repo_user_name: tag.repo_user_name,
            repo_name: tag.repo_name,
            tag_name: tag.tag_name,
        });
    };

    const showArtifactsHandle = (event: React.MouseEvent<HTMLElement, MouseEvent>) => {
        stopPropagation(event);

        dispatch(
            showArtifacts({
                artifacts: artifactsToArtifactPaths(tag.artifacts),
                run_name: tag.run_name,
                workflow_name: tag.workflow_name,
            }),
        );
    };

    return (
        <div className={cn(css.card, className)}>
            <div className={css.topSection}>
                <div className={cn(css.name, 'mono-font')}>{tag.tag_name}</div>

                <Dropdown
                    items={[
                        {
                            children: t('delete'),
                            onClick: deleteHandle,
                            disabled: isDeleting,
                        },
                    ]}
                >
                    <Button
                        className={css.dropdownButton}
                        appearance="gray-transparent"
                        displayAsRound
                        icon={<DotsIcon />}
                        dimension="s"
                    />
                </Dropdown>
            </div>

            <div className={css.run}>{tag.run_name}</div>

            <div className={css.bottomSection}>
                <ul className={css.points}>
                    <li className={css.point}>
                        <ClockIcon width={12} height={12} />
                        {getDateAgoSting(tag.created_at)}
                    </li>

                    {!!tag.artifacts?.length && (
                        <li className={cn(css.point, css.clickable)} onClick={showArtifactsHandle}>
                            <LayersIcon width={11} height={11} />
                            {tag.artifacts.length} {t('artifact', { count: tag.artifacts.length })}
                        </li>
                    )}
                </ul>
            </div>
        </div>
    );
};

export default TagCard;
