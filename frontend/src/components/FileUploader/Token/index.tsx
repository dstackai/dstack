import React, { ReactNode } from 'react';
import Button from '@cloudscape-design/components/button';
import SpaceBetween from '@cloudscape-design/components/space-between';

import styles from './styles.module.scss';

export interface IProps {
    children: ReactNode;
    onClose?: () => void;
}

export const Token: React.FC<IProps> = ({ children, onClose }) => {
    return (
        <div className={styles.tokenPanel}>
            <div style={{ width: '100%' }}> {children} </div>
            {!!onClose && (
                <SpaceBetween size="s">
                    <Button iconName="close" variant="inline-icon" onClick={onClose} ariaLabel="close-token" />
                </SpaceBetween>
            )}
        </div>
    );
};
