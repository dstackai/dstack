import React from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { NavigateLink, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { ROUTES } from 'routes';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<IEvent>[] = [
        {
            id: 'recorded_at',
            header: t('events.recorded_at'),
            cell: (item) => format(new Date(item.recorded_at), DATE_TIME_FORMAT),
        },
        {
            id: 'actor',
            header: t('events.actor'),
            cell: (item) =>
                item.actor_user ? (
                    <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(item.actor_user)}>{item.actor_user}</NavigateLink>
                ) : (
                    '-'
                ),
        },
        {
            id: 'target',
            header: t('events.targets'),
            cell: (item) => {
                return item.targets.map((target) => {
                    switch (target.type) {
                        case 'project':
                            return (
                                <div>
                                    Project{' '}
                                    {target.project_name && (
                                        <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(target.project_name)}>
                                            {target.project_name}
                                        </NavigateLink>
                                    )}
                                </div>
                            );

                        case 'fleet':
                            return (
                                <div>
                                    Fleet{' '}
                                    {target.project_name && (
                                        <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(target.project_name)}>
                                            {target.project_name}
                                        </NavigateLink>
                                    )}
                                    /
                                    <NavigateLink href={ROUTES.FLEETS.DETAILS.FORMAT(target.project_name ?? '', target.id)}>
                                        {target.name}
                                    </NavigateLink>
                                </div>
                            );

                        case 'user':
                            return (
                                <div>
                                    User{' '}
                                    <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(target.name)}>{target.name}</NavigateLink>
                                </div>
                            );

                        case 'instance':
                            return (
                                <div>
                                    Instance{' '}
                                    {target.project_name && (
                                        <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(target.project_name)}>
                                            {target.project_name}
                                        </NavigateLink>
                                    )}
                                    /{target.name}
                                </div>
                            );

                        case 'run':
                            return (
                                <div>
                                    Run{' '}
                                    {target.project_name && (
                                        <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(target.project_name)}>
                                            {target.project_name}
                                        </NavigateLink>
                                    )}
                                    /
                                    <NavigateLink
                                        href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(target.project_name ?? '', target.id)}
                                    >
                                        {target.name}
                                    </NavigateLink>
                                </div>
                            );

                        case 'job':
                            return (
                                <div>
                                    Job{' '}
                                    {target.project_name && (
                                        <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(target.project_name)}>
                                            {target.project_name}
                                        </NavigateLink>
                                    )}
                                    /{target.name}
                                </div>
                            );

                        default:
                            return '---';
                    }
                });
            },
        },
        {
            id: 'message',
            header: t('events.message'),
            cell: ({ message }) => message,
        },
    ];

    return { columns } as const;
};
