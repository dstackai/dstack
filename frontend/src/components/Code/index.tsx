import React from 'react';
import classNames from 'classnames';
import Box from '@cloudscape-design/components/box';

import styles from './styles.module.scss';

export interface Props extends React.PropsWithChildren {
    className?: string;
}

export const Code: React.FC<Props> = ({ children, className }) => {
    return (
        <div className={classNames(styles.code, className)}>
            <Box variant="code" color="text-status-inactive">
                {children}
            </Box>
        </div>
    );
};
