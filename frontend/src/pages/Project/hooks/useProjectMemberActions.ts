import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { useAddProjectMemberMutation, useRemoveProjectMemberMutation } from 'services/project';

export const useProjectMemberActions = () => {
    const { t } = useTranslation();
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

    const handleLeaveProject = async (projectName: string, username: string, onLeaveSuccess?: () => void) => {
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

            // Optionally call the success callback
            onLeaveSuccess?.();
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
        } catch (error: any) {
            console.error('Failed to leave project:', error);

            // Extract the specific error message from the backend
            let errorMessage = t('projects.leave_error');
            if (error?.data?.detail) {
                if (Array.isArray(error.data.detail)) {
                    // Handle array format: [{msg: "error message"}]
                    errorMessage = error.data.detail[0]?.msg || errorMessage;
                } else if (typeof error.data.detail === 'string') {
                    // Handle string format
                    errorMessage = error.data.detail;
                } else if (error.data.detail.msg) {
                    // Handle object format: {msg: "error message"}
                    errorMessage = error.data.detail.msg;
                }
            }

            pushNotification({
                type: 'error',
                content: errorMessage,
            });
        }
    };

    const isMemberActionLoading = isAdding || isRemoving;

    return {
        handleJoinProject,
        handleLeaveProject,
        isMemberActionLoading,
    };
};
