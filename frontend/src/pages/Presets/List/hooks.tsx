import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { format } from 'date-fns';

import type { PropertyFilterProps } from 'components';
import { Button, ListEmptyMessage, NavigateLink } from 'components';

import { DATE_TIME_FORMAT, PRESETS_DOCS_URL } from 'consts';
import { useNotifications } from 'hooks';
import { getServerError, goToUrl } from 'libs';
import {
    getNamePatternFilterRequestParams,
    requestParamsToTokens,
    tokensToRequestParams,
    tokensToSearchParams,
} from 'libs/filters';
import { ROUTES } from 'routes';
import { useDeletePresetMutation } from 'services/preset';
import { useLazyGetProjectsQuery } from 'services/project';
import { useLazyGetUserListQuery } from 'services/user';

type RequestParamsKeys = keyof Pick<TPresetsListRequestParams, 'project_name' | 'username' | 'base'>;

const filterKeys: Record<string, RequestParamsKeys> = {
    PROJECT_NAME: 'project_name',
    USERNAME: 'username',
    BASE: 'base',
};

const MAX_FILTER_OPTIONS = 100;

export const usePresetsTableEmptyMessages = ({
    clearFilter,
    isDisabledClearFilter,
    isPublic,
}: {
    clearFilter?: () => void;
    isDisabledClearFilter?: boolean;
    isPublic: boolean;
}) => {
    const { t } = useTranslation();

    const renderEmptyMessage = (): React.ReactNode => {
        if (isDisabledClearFilter && isPublic) {
            return (
                <ListEmptyMessage
                    title={t('presets.public_empty_message_title')}
                    message={t('presets.public_empty_message_text')}
                />
            );
        }

        if (isDisabledClearFilter) {
            // Presets are created and pushed with the CLI, so there is nothing
            // to create here - the docs are the useful next step.
            return (
                <ListEmptyMessage title={t('presets.empty_message_title')} message={t('presets.empty_message_text')}>
                    <Button variant="primary" external onClick={() => goToUrl(PRESETS_DOCS_URL, true)}>
                        {t('presets.documentation')}
                    </Button>
                </ListEmptyMessage>
            );
        }

        return (
            <ListEmptyMessage title={t('presets.nomatch_message_title')} message={t('presets.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    };

    const renderNoMatchMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('presets.nomatch_message_title')} message={t('presets.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    };

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};

export const useColumnsDefinitions = ({ isPublic }: { isPublic: boolean }) => {
    const { t } = useTranslation();

    const columns = [
        {
            id: 'name',
            header: t('presets.name'),
            // The name says which preset it points at today; the id is what
            // identifies one, so that is what links to it.
            cell: (item: IPreset) => item.name,
        },
        {
            id: 'id',
            header: t('presets.id'),
            cell: (item: IPreset) => (
                <NavigateLink href={ROUTES.PRESETS.DETAILS.FORMAT(item.project_name, item.id)}>{item.id}</NavigateLink>
            ),
        },
        {
            id: 'project',
            header: t('presets.project'),
            cell: (item: IPreset) => (
                <NavigateLink
                    href={
                        isPublic
                            ? `${ROUTES.PRESETS.LIST}?${new URLSearchParams({ project_name: item.project_name })}`
                            : ROUTES.PROJECT.DETAILS.FORMAT(item.project_name)
                    }
                >
                    {item.project_name}
                </NavigateLink>
            ),
        },
        {
            id: 'base',
            header: t('presets.base'),
            cell: (item: IPreset) => item.base,
        },
        {
            id: 'repo',
            header: t('presets.repo'),
            cell: (item: IPreset) => item.repo,
        },
        {
            id: 'user',
            header: t('presets.user'),
            cell: (item: IPreset) =>
                isPublic ? (
                    item.pushed_by
                ) : (
                    <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(item.pushed_by)}>{item.pushed_by}</NavigateLink>
                ),
        },
        {
            id: 'created',
            header: t('presets.created_at'),
            cell: (item: IPreset) => format(new Date(item.created_at), DATE_TIME_FORMAT),
        },
    ];

    return { columns } as const;
};

export const usePresetsDelete = () => {
    const { t } = useTranslation();
    const [request, { isLoading: isDeleting }] = useDeletePresetMutation();
    const [pushNotification] = useNotifications();

    const deletePresets = (presets: IPreset[]) => {
        return Promise.all(
            presets.map((preset) => request({ project_name: preset.project_name, id: preset.id }).unwrap()),
        ).catch((error) => {
            pushNotification({
                type: 'error',
                content: t('common.server_error', { error: getServerError(error) }),
            });
        });
    };

    return { isDeleting, deletePresets } as const;
};

export const useFilters = ({ scope }: { scope: 'public' | 'mine' }) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const propertyFilterQuery = useMemo(
        () => requestParamsToTokens<RequestParamsKeys>({ searchParams, filterKeys }),
        [searchParams],
    );
    const [filteringOptions, setFilteringOptions] = useState<PropertyFilterProps.FilteringOption[]>([]);
    const [filteringStatusType, setFilteringStatusType] = useState<PropertyFilterProps.StatusType | undefined>();
    const [getProjects] = useLazyGetProjectsQuery();
    const [getUsers] = useLazyGetUserListQuery();

    const filteringProperties = [
        {
            key: filterKeys.PROJECT_NAME,
            operators: ['='],
            propertyLabel: 'Project',
            groupValuesLabel: 'Project values',
        },
        {
            key: filterKeys.USERNAME,
            operators: ['='],
            propertyLabel: 'User',
            groupValuesLabel: 'User values',
        },
        {
            key: filterKeys.BASE,
            operators: ['='],
            propertyLabel: 'Base',
            groupValuesLabel: 'Base values',
        },
    ];

    // Projects and users are suggested by the same name-pattern lookups the
    // other list pages use; a base model is typed in, as no API enumerates one.
    const handleLoadItems: PropertyFilterProps['onLoadItems'] = async ({ detail: { filteringProperty, filteringText } }) => {
        setFilteringOptions([]);
        if (scope === 'public') {
            setFilteringStatusType(undefined);
            return;
        }
        setFilteringStatusType('loading');

        try {
            if (filteringProperty?.key === filterKeys.PROJECT_NAME) {
                await getProjects(getNamePatternFilterRequestParams(filteringText, MAX_FILTER_OPTIONS))
                    .unwrap()
                    .then(({ data }) =>
                        data.map(({ project_name }) => ({
                            propertyKey: filterKeys.PROJECT_NAME,
                            value: project_name,
                        })),
                    )
                    .then(setFilteringOptions);
            }

            if (filteringProperty?.key === filterKeys.USERNAME) {
                await getUsers(getNamePatternFilterRequestParams(filteringText, MAX_FILTER_OPTIONS))
                    .unwrap()
                    .then(({ data }) =>
                        data.map(({ username }) => ({
                            propertyKey: filterKeys.USERNAME,
                            value: username,
                        })),
                    )
                    .then(setFilteringOptions);
            }
        } catch {
            setFilteringStatusType('error');
            return;
        }

        setFilteringStatusType(undefined);
    };

    const onChangePropertyFilter: PropertyFilterProps['onChange'] = ({ detail }) => {
        const filteredTokens = detail.tokens.filter((token, tokenIndex) => {
            if (!token.propertyKey) return true;
            return !detail.tokens.some((item, index) => tokenIndex < index && item.propertyKey === token.propertyKey);
        });

        const nextSearchParams = tokensToSearchParams<RequestParamsKeys>(filteredTokens);
        setSearchParams(nextSearchParams);
    };

    const clearFilter = () => {
        setSearchParams({});
    };

    const filteringRequestParams = useMemo(() => {
        return tokensToRequestParams<RequestParamsKeys>({ tokens: propertyFilterQuery.tokens });
    }, [propertyFilterQuery]);

    const isDisabledClearFilter = !propertyFilterQuery.tokens.length;

    return {
        filteringRequestParams,
        clearFilter,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        isDisabledClearFilter,
        filteringStatusType,
        handleLoadItems,
    } as const;
};
