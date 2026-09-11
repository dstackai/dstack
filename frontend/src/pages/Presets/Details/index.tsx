import React from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate, useParams } from 'react-router-dom';
import { format } from 'date-fns';

import {
    Alert,
    Box,
    ButtonWithConfirmation,
    ColumnLayout,
    Container,
    ContentLayout,
    DetailsHeader,
    Header,
    Loader,
    NavigateLink,
    SpaceBetween,
    Tabs,
} from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useBreadcrumbs, useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import { useDeletePresetMutation, useGetPresetQuery } from 'services/preset';

import { PresetBenchmark } from './Benchmark';
import { PresetConstraints } from './Constraints';
import { Deploy } from './Deploy';

enum PresetTab {
    Details = 'details',
    VerifiedOn = 'verified-on',
    Inspect = 'inspect',
}

export const PresetDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const paramProjectName = params.projectName ?? '';
    const paramPresetId = params.presetId ?? '';

    const {
        currentData: data,
        isLoading,
        isFetching,
        error,
    } = useGetPresetQuery({
        project_name: paramProjectName,
        id: paramPresetId,
    });

    const [deletePreset, { isLoading: isDeleting }] = useDeletePresetMutation();
    const isLoadingPreset = isLoading || (isFetching && !data);
    const canDelete = !!data?.can_delete;

    useBreadcrumbs([
        {
            text: t('navigation.presets'),
            href: ROUTES.PRESETS.LIST,
        },
        {
            text: data?.name ?? paramPresetId,
            href: ROUTES.PRESETS.DETAILS.FORMAT(paramProjectName, paramPresetId),
        },
    ]);

    const deleteClickHandle = () => {
        if (!canDelete || !data) return;
        deletePreset({ project_name: paramProjectName, id: data.id })
            .unwrap()
            .then(() => navigate(ROUTES.PRESETS.LIST))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    };

    return (
        <ContentLayout
            header={
                <DetailsHeader
                    title={data?.name ?? paramPresetId}
                    actionButtons={
                        canDelete && !error ? (
                            <ButtonWithConfirmation
                                disabled={isDeleting || !data}
                                formAction="none"
                                onClick={deleteClickHandle}
                                confirmTitle={t('presets.delete_confirm_title')}
                                confirmContent={t('presets.delete_confirm_message')}
                            >
                                {t('common.delete')}
                            </ButtonWithConfirmation>
                        ) : undefined
                    }
                />
            }
        >
            {isLoadingPreset && !data && <Loader />}

            {!isLoadingPreset && (error || !data) && (
                <Alert type="error" header={t('presets.unavailable_title')}>
                    {t('presets.unavailable_message')}
                </Alert>
            )}

            {data && !error && (
                <SpaceBetween size="l">
                    {/* Nothing else on the page explains an empty name. */}
                    {!data.name && <Alert type="info">{t('presets.superseded_alert')}</Alert>}

                    <Tabs
                        withNavigation
                        tabs={[
                            {
                                label: t('presets.details'),
                                id: PresetTab.Details,
                                href: ROUTES.PRESETS.DETAILS.FORMAT(paramProjectName, paramPresetId),
                            },
                            {
                                label: t('presets.verified_on'),
                                id: PresetTab.VerifiedOn,
                                href: ROUTES.PRESETS.DETAILS.VERIFIED_ON.FORMAT(paramProjectName, paramPresetId),
                            },
                            {
                                label: t('presets.inspect'),
                                id: PresetTab.Inspect,
                                href: ROUTES.PRESETS.DETAILS.INSPECT.FORMAT(paramProjectName, paramPresetId),
                            },
                        ]}
                    />

                    <Outlet />
                </SpaceBetween>
            )}
        </ContentLayout>
    );
};

export const PresetDetailsOverview: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramPresetId = params.presetId ?? '';

    const { data, isLoading } = useGetPresetQuery({
        project_name: paramProjectName,
        id: paramPresetId,
    });

    if (isLoading || !data)
        return (
            <Container>
                <Loader />
            </Container>
        );

    return (
        <SpaceBetween size="l">
            <Container header={<Header variant="h2">{t('presets.details')}</Header>}>
                <ColumnLayout columns={4} variant="text-grid">
                    <div>
                        <Box variant="awsui-key-label">{t('presets.name')}</Box>
                        <div>{data.name}</div>
                    </div>
                    <div>
                        <Box variant="awsui-key-label">{t('presets.id')}</Box>
                        <div>{data.id}</div>
                    </div>
                    <div>
                        <Box variant="awsui-key-label">{t('presets.base')}</Box>
                        <div>{data.base}</div>
                    </div>
                    <div>
                        <Box variant="awsui-key-label">{t('presets.repo')}</Box>
                        <div>{data.repo}</div>
                    </div>
                    <div>
                        <Box variant="awsui-key-label">{t('presets.project')}</Box>
                        <div>
                            <NavigateLink
                                href={
                                    data.can_delete
                                        ? ROUTES.PROJECT.DETAILS.FORMAT(data.project_name)
                                        : `${ROUTES.PRESETS.LIST}?${new URLSearchParams({ project_name: data.project_name })}`
                                }
                            >
                                {data.project_name}
                            </NavigateLink>
                        </div>
                    </div>
                    <div>
                        <Box variant="awsui-key-label">{t('presets.user')}</Box>
                        <div>
                            {data.can_delete ? (
                                <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(data.pushed_by)}>{data.pushed_by}</NavigateLink>
                            ) : (
                                data.pushed_by
                            )}
                        </div>
                    </div>
                    <div>
                        <Box variant="awsui-key-label">{t('presets.created_at')}</Box>
                        <div>{format(new Date(data.created_at), DATE_TIME_FORMAT)}</div>
                    </div>
                </ColumnLayout>
            </Container>

            <PresetConstraints />

            <PresetBenchmark />

            <Deploy preset={data} />
        </SpaceBetween>
    );
};
