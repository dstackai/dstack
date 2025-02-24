import React, { useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { format } from 'date-fns';

import { Button, ListEmptyMessage, NavigateLink, SelectCSDProps, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useProjectFilter } from 'hooks/useProjectFilter';
import { ROUTES } from 'routes';

import { getModelGateway } from '../helpers';

import { IModelExtended } from './types';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<IModelExtended>[] = [
        {
            id: 'model_name',
            header: t('models.model_name'),
            cell: (item) => {
                return (
                    <NavigateLink href={ROUTES.MODELS.DETAILS.FORMAT(item.project_name, item.run_name)}>
                        {item.name}
                    </NavigateLink>
                );
            },
        },
        {
            id: 'type',
            header: `${t('models.type')}`,
            cell: (item) => item.type,
        },
        {
            id: 'url',
            header: `${t('models.url')}`,
            cell: (item) => getModelGateway(item.base_url),
        },
        {
            id: 'run',
            header: `${t('models.run')}`,
            cell: (item) => (
                <NavigateLink
                    href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(item.project_name, item.run_name ?? 'No run name')}
                >
                    {item.run_name}
                </NavigateLink>
            ),
        },
        {
            id: 'resources',
            header: `${t('models.resources')}`,
            cell: (item) => item.resources,
        },
        {
            id: 'price',
            header: `${t('models.price')}`,
            cell: (item) => (item.price ? `$${item.price}` : null),
        },
        {
            id: 'submitted_at',
            header: `${t('models.submitted_at')}`,
            cell: (item) => format(new Date(item.submitted_at), DATE_TIME_FORMAT),
        },
        {
            id: 'user',
            header: `${t('models.user')}`,
            cell: (item) => <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(item.user)}>{item.user}</NavigateLink>,
        },
        {
            id: 'repository',
            header: `${t('models.repository')}`,
            cell: (item) => item.repository,
        },
        {
            id: 'backend',
            header: `${t('models.backend')}`,
            cell: (item) => item.backend,
        },
    ];

    return { columns } as const;
};

export const useEmptyMessages = ({
    clearFilter,
    isDisabledClearFilter,
}: {
    clearFilter?: () => void;
    isDisabledClearFilter?: boolean;
}) => {
    const { t } = useTranslation();

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('models.empty_message_title')} message={t('models.empty_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilter, isDisabledClearFilter]);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('models.nomatch_message_title')} message={t('models.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilter, isDisabledClearFilter]);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};

type Args = {
    projectSearchKey?: string;
    localStorePrefix?: string;
};

export const useFilters = ({ projectSearchKey, localStorePrefix = 'models-list-page' }: Args) => {
    const [searchParams] = useSearchParams();
    const { selectedProject, setSelectedProject, projectOptions } = useProjectFilter({ localStorePrefix });

    const setSelectedOptionFromParams = (
        searchKey: string,
        options: SelectCSDProps.Options | null,
        set: (option: SelectCSDProps.Option) => void,
    ) => {
        const searchValue = searchParams.get(searchKey);

        if (!searchValue || !options?.length) return;

        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        const selectedOption = options.find((option) => option?.value === searchValue);

        if (selectedOption) set(selectedOption);
    };

    useEffect(() => {
        if (!projectSearchKey) return;

        setSelectedOptionFromParams(projectSearchKey, projectOptions, setSelectedProject);
    }, [searchParams, projectSearchKey, projectOptions]);

    const clearSelected = () => {
        setSelectedProject(null);
    };

    const setSelectedProjectHandle = (project: SelectCSDProps.Option | null) => {
        setSelectedProject(project);
    };

    return {
        projectOptions,
        selectedProject,
        setSelectedProject: setSelectedProjectHandle,
        clearSelected,
    } as const;
};
