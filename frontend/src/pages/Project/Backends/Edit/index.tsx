import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { pick } from 'lodash';

import { Container, Header, Loader } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import {
    // useGetBackendConfigQuery,
    useGetBackendYamlQuery,
    // useUpdateBackendMutation,
    useUpdateBackendViaYamlMutation,
} from 'services/backend';

// import { BackendForm } from '../Form';
// import { prepareBackendConfigForApi } from '../Form/helpers';
import { YAMLForm } from '../YAMLForm';

export const BackendEdit: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramBackendName = params.backend ?? '';
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    // const [updateProject, { isLoading: isBackendUpdating }] = useUpdateBackendMutation();
    const [updateBackendYamlConfig, { isLoading: isBackendYamlConfigUpdating }] = useUpdateBackendViaYamlMutation();

    // const { data, isLoading } = useGetBackendConfigQuery({ projectName: paramProjectName, backendName: paramBackendName });

    const {
        data: backendYamlData,
        isLoading: isLoadingYaml,
        isFetching: isFetchingYaml,
    } = useGetBackendYamlQuery(
        {
            projectName: paramProjectName,
            backendName: paramBackendName,
        },
        {
            refetchOnMountOrArgChange: true,
        },
    );

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.FORMAT(paramProjectName),
        },
        {
            text: t('projects.settings'),
            href: ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName),
        },
        {
            text: t('backend.edit_backend'),
            href: ROUTES.PROJECT.BACKEND.ADD.FORMAT(paramProjectName),
        },
    ]);

    const onCancelHandler = () => {
        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    // const onSubmitHandler = async (backend: TBackendConfig): Promise<TBackendConfig> => {
    //     const request = updateProject({
    //         projectName: paramProjectName,
    //         config: prepareBackendConfigForApi(backend),
    //     }).unwrap();
    //
    //     request
    //         .then(() => {
    //             pushNotification({
    //                 type: 'success',
    //                 content: t('backend.edit.success_notification'),
    //             });
    //
    //             navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    //         })
    //         .catch(console.log);
    //
    //     return request;
    // };

    const onSubmitYaml = async (backend: IBackendConfigYaml): Promise<void> => {
        const request = updateBackendYamlConfig({
            projectName: paramProjectName,
            backend,
        }).unwrap();

        request
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('backend.edit.success_notification'),
                });
            })
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });

        return request;
    };

    const onSubmitYamlHandler = async (backend: IBackendConfigYaml): Promise<void> => {
        const request = onSubmitYaml(backend);
        request.then(() => navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName)));
        return request;
    };

    const onApplyYamlHandler = async (backend: IBackendConfigYaml): Promise<void> => onSubmitYaml(backend);

    if (isLoadingYaml || isFetchingYaml)
        return (
            <Container>
                <Loader />
            </Container>
        );

    return (
        <Container header={<Header variant="h2">{t('backend.edit_backend')}</Header>}>
            {/*{data && (*/}
            {/*    <BackendForm*/}
            {/*        initialValues={data}*/}
            {/*        loading={isBackendUpdating}*/}
            {/*        onSubmit={onSubmitHandler}*/}
            {/*        onCancel={onCancelHandler}*/}
            {/*    />*/}
            {/*)}*/}

            {backendYamlData && (
                <YAMLForm
                    initialValues={pick(backendYamlData, 'config_yaml')}
                    loading={isBackendYamlConfigUpdating}
                    onApply={onApplyYamlHandler}
                    onSubmit={onSubmitYamlHandler}
                    onCancel={onCancelHandler}
                />
            )}
        </Container>
    );
};
