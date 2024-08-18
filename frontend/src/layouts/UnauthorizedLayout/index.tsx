import React from 'react';

import styles from './styles.module.scss';

export interface UnauthorizedLayoutProps {
    children?: React.ReactNode;
}

export const UnauthorizedLayout: React.FC<UnauthorizedLayoutProps> = ({ children }) => {
    return <div className={styles.layout}>{children}</div>;
};
