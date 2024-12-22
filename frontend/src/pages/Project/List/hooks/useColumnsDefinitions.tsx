import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

// import { useNavigate } from 'react-router-dom';
import { /*Button,*/ NavigateLink } from 'components';

// import { ButtonWithConfirmation } from 'components/ButtonWithConfirmation';
import { ROUTES } from 'routes';

// import { useCheckAvailableProjectPermission } from '../../hooks/useCheckAvailableProjectPermission';
import styles from '../styles.module.scss';

type hookArgs = {
    loading?: boolean;
    onDeleteClick?: (project: IProject) => void;
};

export const useColumnsDefinitions = ({ loading, onDeleteClick }: hookArgs) => {
    const { t } = useTranslation();
    // const navigate = useNavigate();

    // const { isAvailableDeletingPermission } = useCheckAvailableProjectPermission();
    //
    // const goToSettings = (project: IProject) => {
    //     navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(project.project_name));
    // };

    const columns = useMemo(() => {
        return [
            {
                id: 'project_name',
                header: `${t('projects.edit.project_name')}`,
                cell: (project: IProject) => (
                    <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(project.project_name)}>
                        {project.project_name}
                    </NavigateLink>
                ),
            },
            {
                id: 'owner.username',
                header: `${t('projects.edit.owner')}`,
                cell: (project: IProject) => (
                    <div className={styles.cell}>
                        <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(project.owner.username)}>
                            {project.owner.username}
                        </NavigateLink>

                        {/*<div className={styles.contextMenu}>*/}
                        {/*    <Button*/}
                        {/*        disabled={loading}*/}
                        {/*        formAction="none"*/}
                        {/*        onClick={() => goToSettings(project)}*/}
                        {/*        variant="icon"*/}
                        {/*        iconName="settings"*/}
                        {/*    />*/}

                        {/*    {onDeleteClick && (*/}
                        {/*        <ButtonWithConfirmation*/}
                        {/*            disabled={loading || !isAvailableDeletingPermission(project)}*/}
                        {/*            formAction="none"*/}
                        {/*            onClick={() => onDeleteClick(project)}*/}
                        {/*            variant="icon"*/}
                        {/*            iconName="remove"*/}
                        {/*            confirmTitle={t('projects.edit.delete_project_confirm_title')}*/}
                        {/*            confirmContent={t('projects.edit.delete_project_confirm_message')}*/}
                        {/*        />*/}
                        {/*    )}*/}
                        {/*</div>*/}
                    </div>
                ),
            },
        ];
    }, [loading, onDeleteClick]);

    return { columns } as const;
};
