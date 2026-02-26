import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { format } from 'date-fns';

import { Box, ColumnLayout, Container, Header, Loader, NavigateLink, StatusIndicator } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { formatBackend, getStatusIconType } from 'libs/fleet';
import { getHealthStatusIconType, prettyEnumValue } from 'libs/instance';
import { formatResources } from 'libs/resources';
import { ROUTES } from 'routes';
import { useGetInstanceDetailsQuery } from 'services/instance';

export const InstanceDetails = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramInstanceId = params.instanceId ?? '';
    const paramProjectName = params.projectName ?? '';

    const { data, isLoading } = useGetInstanceDetailsQuery(
        {
            projectName: paramProjectName,
            instanceId: paramInstanceId,
        },
        {
            refetchOnMountOrArgChange: true,
        },
    );

    return (
        <>
            {isLoading && (
                <Container>
                    <Loader />
                </Container>
            )}

            {data && (
                <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                    <ColumnLayout columns={4} variant="text-grid">
                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.project')}</Box>
                            <div>
                                <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(data.project_name)}>
                                    {data.project_name}
                                </NavigateLink>
                            </div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.fleet')}</Box>
                            <div>
                                {data.fleet_name && data.fleet_id ? (
                                    <NavigateLink
                                        href={ROUTES.FLEETS.DETAILS.FORMAT(data.project_name, data.fleet_id)}
                                    >
                                        {data.fleet_name}
                                    </NavigateLink>
                                ) : (
                                    '-'
                                )}
                            </div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.status')}</Box>
                            <div>
                                <StatusIndicator type={getStatusIconType(data.status)}>
                                    {(data.status === 'idle' || data.status === 'busy') &&
                                    data.total_blocks !== null &&
                                    data.total_blocks > 1
                                        ? `${data.busy_blocks}/${data.total_blocks} Busy`
                                        : prettyEnumValue(data.status)}
                                </StatusIndicator>
                            </div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('projects.run.error')}</Box>
                            <div>
                                {data.unreachable ? (
                                    <StatusIndicator type="error">Unreachable</StatusIndicator>
                                ) : data.health_status !== 'healthy' ? (
                                    <StatusIndicator type={getHealthStatusIconType(data.health_status)}>
                                        {prettyEnumValue(data.health_status)}
                                    </StatusIndicator>
                                ) : (
                                    '-'
                                )}
                            </div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.started')}</Box>
                            <div>{format(new Date(data.created), DATE_TIME_FORMAT)}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.finished_at')}</Box>
                            <div>
                                {data.finished_at ? format(new Date(data.finished_at), DATE_TIME_FORMAT) : '-'}
                            </div>
                        </div>

                        {data.termination_reason && (
                            <div>
                                <Box variant="awsui-key-label">{t('fleets.instances.termination_reason')}</Box>
                                <div>
                                    {data.termination_reason_message ?? prettyEnumValue(data.termination_reason)}
                                </div>
                            </div>
                        )}

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.resources')}</Box>
                            <div>{data.instance_type ? formatResources(data.instance_type.resources) : '-'}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.backend')}</Box>
                            <div>{formatBackend(data.backend)}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.region')}</Box>
                            <div>{data.region ?? '-'}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.instance_type')}</Box>
                            <div>{data.instance_type?.name ?? '-'}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.spot')}</Box>
                            <div>{data.instance_type?.resources.spot ? t('common.yes') : t('common.no')}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.price')}</Box>
                            <div>{typeof data.price === 'number' ? `$${data.price}` : '-'}</div>
                        </div>

                        {data.total_blocks !== null && (
                            <div>
                                <Box variant="awsui-key-label">{t('fleets.instances.blocks')}</Box>
                                <div>{data.total_blocks}</div>
                            </div>
                        )}

                        <div>
                            <Box variant="awsui-key-label">{t('fleets.instances.hostname')}</Box>
                            <div>{data.hostname ?? '-'}</div>
                        </div>
                    </ColumnLayout>
                </Container>
            )}
        </>
    );
};
