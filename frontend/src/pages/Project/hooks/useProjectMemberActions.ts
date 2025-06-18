import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useAddProjectMemberMutation, useRemoveProjectMemberMutation } from 'services/project';

export const useProjectMemberActions = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [addMember, { isLoading: isAdding }] = useAddProjectMemberMutation();
    const [removeMember, { isLoading: isRemoving }] = useRemoveProjectMemberMutation();

    const handleJoinProject = async (projectName: string, username: string) => {
        if (!username || !projectName) return;
        
        try {
            await addMember({
                project_name: projectName,
                username: username,
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

    const handleLeaveProject = async (projectName: string, username: string) => {
        if (!username || !projectName) return;
        
        try {
            await removeMember({
                project_name: projectName,
                username: username,
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

    const isMemberActionLoading = isAdding || isRemoving;

    return {
        handleJoinProject,
        handleLeaveProject,
        isMemberActionLoading
    };
}; 
