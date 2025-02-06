import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Container, Header } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import {
    // useCreateBackendMutation,
    useCreateBackendViaYamlMutation,
} from 'services/backend';

// import { BackendForm } from '../Form';
// import { prepareBackendConfigForApi } from '../Form/helpers';
import { YAMLForm } from '../YAMLForm';

export const BackendAdd: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();

    // const [createBackend, { isLoading }] = useCreateBackendMutation();
    const [createBackendViaYaml, { isLoading: isCreatingViaYaml }] = useCreateBackendViaYamlMutation();

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
            text: t('backend.add_backend'),
            href: ROUTES.PROJECT.BACKEND.ADD.FORMAT(paramProjectName),
        },
    ]);

    const onCancelHandler = () => {
        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    // const onSubmitHandler = (backend: TBackendConfig) => {
    //     const request = createBackend({
    //         projectName: paramProjectName,
    //         config: prepareBackendConfigForApi(backend),
    //     }).unwrap();
    //
    //     request
    //         .then(() => {
    //             pushNotification({
    //                 type: 'success',
    //                 content: t('backend.create.success_notification'),
    //             });
    //
    //             navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    //         })
    //         .catch((error: never) => {
    //             console.log(error);
    //         });
    //
    //     return request;
    // };

    const onSubmitYamlHandler = (backend: IBackendConfigYaml) => {
        const request = createBackendViaYaml({
            projectName: paramProjectName,
            backend,
        }).unwrap();

        request
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('backend.create.success_notification'),
                });

                navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
            })
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });

        return request;
    };

    return (
        <Container header={<Header variant="h2">{t('backend.add_backend')}</Header>}>
            {/*<BackendForm loading={isLoading} onSubmit={onSubmitHandler} onCancel={onCancelHandler} />*/}
            <YAMLForm loading={isCreatingViaYaml} onSubmit={onSubmitYamlHandler} onCancel={onCancelHandler} />
        </Container>
    );
};
