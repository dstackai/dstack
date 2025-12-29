import React from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';

import type { ButtonProps } from 'components';
import { Alert, AlertProps, Button } from 'components';

import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { goToUrl } from 'libs';

import styles from './styles.module.scss';

type NoFleetProjectAlertProps = {
    show?: boolean;
    projectName: string;
    className?: string;
    dismissible?: boolean;
};

export const NoFleetProjectAlert: React.FC<NoFleetProjectAlertProps> = ({ projectName, show, className, dismissible }) => {
    const { t } = useTranslation();
    const [dontShowAgain, setDontShowAgain] = useLocalStorageState(`noFleetProjectAlert-${projectName}`, false);

    const onCreateAFleet: ButtonProps['onClick'] = (event) => {
        event.preventDefault();
        goToUrl('https://dstack.ai/docs/quickstart/#create-a-fleet', true);
    };

    const onDismiss: AlertProps['onDismiss'] = () => setDontShowAgain(true);

    if (!show || dontShowAgain) {
        return null;
    }

    return (
        <div className={cn(styles.alertBox, className)}>
            <Alert
                header={t('fleets.no_alert.title')}
                type="info"
                dismissible={dismissible}
                onDismiss={onDismiss}
                action={
                    <Button iconName="external" formAction="none" onClick={onCreateAFleet}>
                        {t('fleets.no_alert.button_title')}
                    </Button>
                }
            >
                The project <code>{projectName}</code> has no fleets. Create one before submitting a run.
            </Alert>
        </div>
    );
};
