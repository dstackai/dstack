import React from 'react';

import { AppLayout, Spinner } from 'components';

import styles from './styles.module.scss';

export const Loading: React.FC = () => {
    return (
        <AppLayout
            toolsHide
            navigationHide
            disableContentPaddings
            content={
                <div className={styles.spinner}>
                    <Spinner size="large" />
                </div>
            }
        />
    );
};
