import React from 'react';
import cn from 'classnames';

import { ReactComponent as ThemeIcon } from 'assets/icons/theme.svg';
import styles from './index.module.scss';

export const DarkThemeIcon: React.FC = () => {
    return (
        <div className={styles.themeIcon}>
            <div className={cn(styles.switcher, styles.on)} />
            <ThemeIcon className={styles.icon} />
        </div>
    );
};

export const LightThemeIcon: React.FC = () => {
    return (
        <div className={styles.themeIcon}>
            <div className={cn(styles.switcher, styles.of)} />
            <ThemeIcon className={styles.icon} />
        </div>
    );
};
