import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate, useParams } from 'react-router-dom';

import { Button, ContentLayout, DetailsHeader } from 'components';

import { useAppSelector, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useAddProjectMemberMutation, useGetProjectQuery, useRemoveProjectMemberMutation } from 'services/project';

import { selectUserData } from 'App/slice';

import { useProjectMemberActions } from '../hooks/useProjectMemberActions';
import { getProjectRoleByUserName } from '../utils';

export const ProjectDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const navigate = useNavigate();
    const paramProjectName = params.projectName ?? '';
    const userData = useAppSelector(selectUserData);
    const { handleJoinProject, handleLeaveProject, isMemberActionLoading } = useProjectMemberActions();

    const { data: project } = useGetProjectQuery({ name: paramProjectName });

    const currentUserRole = useMemo(() => {
        if (!userData?.username || !project) return null;
        return getProjectRoleByUserName(project, userData.username);
    }, [project, userData?.username]);

    const isProjectOwner = userData?.username === project?.owner.username;

    const isMember = currentUserRole !== null;

    return (
        <ContentLayout header={<DetailsHeader title={paramProjectName} />}>
            <Outlet />
        </ContentLayout>
    );
};
