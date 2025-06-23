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

    const renderJoinLeaveButton = () => {
        // Only show button if user is authenticated and project is loaded
        if (!userData?.username || !project) return null;

        if (!isMember) {
            return (
                <Button
                    onClick={() => handleJoinProject(project.project_name, userData.username!)}
                    disabled={isMemberActionLoading}
                    variant="primary"
                >
                    {isMemberActionLoading ? t('common.loading') : t('projects.join')}
                </Button>
            );
        } else {
            // Check if user is the last admin - if so, don't show leave button
            const adminCount = project.members.filter(member => member.project_role === 'admin').length;
            const isLastAdmin = currentUserRole === 'admin' && adminCount <= 1;
            
            if (isLastAdmin) {
                // Don't show leave button for the last admin
                return null;
            }
            
            // Allow leaving for all other members
            return (
                <Button
                    onClick={() => handleLeaveProject(project.project_name, userData.username!, () => navigate(ROUTES.PROJECT.LIST))}
                    disabled={isMemberActionLoading}
                    variant="normal"
                >
                    {isMemberActionLoading 
                            ? t('common.loading') 
                            : t('projects.leave')
                    }
                </Button>
            );
        }
    };

    return (
        <ContentLayout 
            header={
                <DetailsHeader 
                    title={paramProjectName} 
                    actionButtons={renderJoinLeaveButton()}
                />
            }
        >
            <Outlet />
        </ContentLayout>
    );
};
