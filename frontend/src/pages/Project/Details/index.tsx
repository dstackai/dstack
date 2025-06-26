import React, { useMemo } from 'react';
import { Outlet, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Button, ContentLayout, DetailsHeader } from 'components';

import { useAppSelector, useNotifications } from 'hooks';
import { selectUserData } from 'App/slice';
import { ROUTES } from 'routes';
import { useGetProjectQuery, useAddProjectMemberMutation, useRemoveProjectMemberMutation } from 'services/project';
import { getProjectRoleByUserName } from '../utils';
import { useProjectMemberActions } from '../hooks/useProjectMemberActions';

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
        <ContentLayout header={<DetailsHeader title={paramProjectName}/>}>
            <Outlet />
        </ContentLayout>
    );
};
