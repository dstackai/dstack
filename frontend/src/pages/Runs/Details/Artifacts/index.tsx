import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import classNames from 'classnames';

import {
    BreadcrumbGroup,
    BreadcrumbGroupProps,
    Button,
    Header,
    Link,
    LinkProps,
    ListEmptyMessage,
    Table,
    TextFilter,
} from 'components';

import { useCollection } from 'hooks';
import { formatBytes } from 'libs';
import { useGetArtifactsQuery } from 'services/artifact';

import { IProps, ITableItem } from './types';

import styles from './styles.module.scss';

export const Artifacts: React.FC<IProps> = ({ className, ...props }) => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = props.project_name ?? params.projectName ?? '';
    const paramRunName = props.run_name ?? params.runName ?? '';
    const [globalPath, setGlobalPath] = useState<string[]>([]);
    const [selectedArtifactPath, setSelectedArtifactPath] = useState<string>('');

    const { data, isLoading, isFetching } = useGetArtifactsQuery({
        name: paramProjectName,
        run_name: paramRunName,
        prefix: selectedArtifactPath + globalPath.join('/'),
        recursive: false,
    });

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage
                title={t('projects.artifact.empty_message_title')}
                message={t('projects.artifact.empty_message_text')}
            />
        );
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <ListEmptyMessage
                title={t('projects.artifact.nomatch_message_title')}
                message={t('projects.artifact.nomatch_message_text')}
            >
                <Button onClick={onClearFilter}>{t('common.clearFilter')}</Button>
            </ListEmptyMessage>
        );
    };

    const formatListItems = (): ITableItem[] => {
        let items: ITableItem[] = [];

        if (!data) return items;

        if (!selectedArtifactPath) {
            items = data.map((a) => ({
                name: a.name.replace(/\/$/, ''),
                path: a.path,
                type: 'Folder',
                size: null,
            }));
        } else {
            // items = [
            //     {
            //         name: '/',
            //         path: '..',
            //         type: 'Folder',
            //         size: null,
            //     },
            // ];

            data.forEach((a) => {
                const sortedFiles = [...a.files].sort((a, b) => {
                    if (a.filesize_in_bytes !== null && b.filesize_in_bytes === null) return 1;
                    if (a.filesize_in_bytes === null && b.filesize_in_bytes !== null) return -1;

                    return 0;
                });

                sortedFiles.forEach((f) => {
                    let path = f.filepath;

                    if (f.filesize_in_bytes !== null) {
                        const pathByArray = f.filepath.split('/');
                        path = pathByArray[pathByArray.length - 1];
                    }

                    items.push({
                        name: path.replace(/\/$/, ''),
                        path: path,
                        type: f.filesize_in_bytes === null ? 'Folder' : 'File',
                        size: f.filesize_in_bytes,
                    });
                });
            });
        }

        return items;
    };

    const { items, actions, filterProps, filteredItemsCount, collectionProps } = useCollection(formatListItems(), {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(() => actions.setFiltering('')),
        },
        selection: {},
    });

    const getLinkClickHandle =
        (path: string): LinkProps['onFollow'] =>
        (event) => {
            event.preventDefault();

            if (path === '..') {
                if (globalPath.length) {
                    setGlobalPath((oldGlobalPath) => oldGlobalPath.slice(0, -1));
                } else {
                    setSelectedArtifactPath('');
                }

                return;
            }

            if (!selectedArtifactPath) {
                setSelectedArtifactPath(path);
                return;
            }

            setGlobalPath((oldGlobalPath) => [...oldGlobalPath, path]);
        };

    const COLUMN_DEFINITIONS = [
        {
            id: 'name',
            header: t('projects.artifact.name'),
            cell: (item: ITableItem) => {
                if (item.type === 'Folder') return <Link onFollow={getLinkClickHandle(item.path)}>{item.name}</Link>;

                return item.name;
            },
        },
        {
            id: 'type',
            header: t('projects.artifact.type'),
            cell: (item: ITableItem) => item.type,
        },
        {
            id: 'size',
            header: t('projects.artifact.size'),
            cell: (item: ITableItem) => (item.size ? formatBytes(item.size) : '-'),
        },
    ];

    const onFollowHandler: BreadcrumbGroupProps['onFollow'] = (event) => {
        event.preventDefault();

        if (event.detail.href === '/') {
            setSelectedArtifactPath('');
            setGlobalPath([]);
        }

        const path = event.detail.href.replace(new RegExp(`^${selectedArtifactPath}`), '');

        setGlobalPath(
            path
                .split('/')
                .filter(Boolean)
                .map((i) => i + '/'),
        );
    };

    const getBreadcrumbs = (): BreadcrumbGroupProps['items'] => {
        const crumbs = [...(selectedArtifactPath ? [selectedArtifactPath] : []), ...globalPath].reduce(
            (result, item, index) => {
                result.push({
                    text: item.replace(/\/$/, ''),
                    href: index ? result[index - 1].href + item : item,
                });

                return result;
            },
            [] as { text: string; href: string }[],
        );

        return [
            {
                text: t('projects.artifact.list_page_title'),
                href: '/',
            },

            ...crumbs,
        ];
    };

    return (
        <div className={classNames(styles.artifacts, className)}>
            <Table
                {...collectionProps}
                trackBy="name"
                loading={isLoading || isFetching}
                loadingText={t('common.loading')}
                columnDefinitions={COLUMN_DEFINITIONS}
                items={items}
                header={
                    <div>
                        <Header variant="h2" counter={`(${items?.length})`}>
                            {t('common.objects_other')}
                        </Header>

                        <BreadcrumbGroup items={getBreadcrumbs()} onFollow={onFollowHandler} />
                    </div>
                }
                filter={
                    <TextFilter
                        {...filterProps}
                        filteringPlaceholder={t('projects.artifact.search_placeholder')}
                        countText={t('common.match_count_with_value', { count: filteredItemsCount })}
                        disabled={isLoading}
                    />
                }
            />
        </div>
    );
};
