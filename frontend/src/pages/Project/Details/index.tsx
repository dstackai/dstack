import React, { useMemo } from 'react';
import { Outlet, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Button, ContentLayout, DetailsHeader } from 'components';

import { useAppSelector, useNotifications } from 'hooks';
import { selectUserData } from 'App/slice';
import { ROUTES } from 'routes';
import { useGetProjectQuery, useAddProjectMemberMutation, useRemoveProjectMemberMutation } from 'services/project';
import { getProjectRoleByUserName } from '../utils';

export const ProjectDetails: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const navigate = useNavigate();
    const paramProjectName = params.projectName ?? '';
    const [pushNotification] = useNotifications();
    const userData = useAppSelector(selectUserData);
    
    const { data: project } = useGetProjectQuery({ name: paramProjectName });
    const [addMember, { isLoading: isAdding }] = useAddProjectMemberMutation();
    const [removeMember, { isLoading: isRemoving }] = useRemoveProjectMemberMutation();

    const currentUserRole = useMemo(() => {
        if (!userData?.username || !project) return null;
        return getProjectRoleByUserName(project, userData.username);
    }, [project, userData?.username]);

    const isProjectOwner = useMemo(() => {
        return userData?.username === project?.owner.username;
    }, [userData?.username, project?.owner.username]);

    const isMember = currentUserRole !== null;
    const isMemberActionLoading = isAdding || isRemoving;

    const handleJoinProject = async () => {
        if (!userData?.username || !project) return;
        
        try {
            await addMember({
                project_name: project.project_name,
                username: userData.username,
                project_role: 'user',
            }).unwrap();
            
            pushNotification({
                type: 'success',
                content: t('projects.join_success'),
            });
        } catch (error) {
            console.error('Failed to join project:', error);
            pushNotification({
                type: 'error',
                content: t('projects.join_error'),
            });
        }
    };

    const handleLeaveProject = async () => {
        if (!userData?.username || !project) return;
        
        try {
            await removeMember({
                project_name: project.project_name,
                username: userData.username,
            }).unwrap();
            
            pushNotification({
                type: 'success',
                content: t('projects.leave_success'),
            });
            
            // Redirect to project list after successfully leaving
            navigate(ROUTES.PROJECT.LIST);
        } catch (error) {
            console.error('Failed to leave project:', error);
            pushNotification({
                type: 'error',
                content: t('projects.leave_error'),
            });
        }
    };

    const renderJoinLeaveButton = () => {
        // Only show button if user is authenticated and project is loaded
        if (!userData?.username || !project) return null;

        if (!isMember) {
            return (
                <Button
                    onClick={handleJoinProject}
                    disabled={isMemberActionLoading}
                    variant="primary"
                >
                    {isMemberActionLoading ? t('common.loading') : t('projects.join')}
                </Button>
            );
        } else {
            // Prevent owners and admins from leaving their projects
            const canLeave = !isProjectOwner && currentUserRole !== 'admin';
            
            return (
                <Button
                    onClick={handleLeaveProject}
                    disabled={isMemberActionLoading || !canLeave}
                    variant="normal"
                >
                    {!canLeave 
                        ? t('projects.owner_cannot_leave')
                        : isMemberActionLoading 
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
