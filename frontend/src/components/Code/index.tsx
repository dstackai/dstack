import React from 'react';
import classNames from 'classnames';
import Box from '@cloudscape-design/components/box';

import styles from './styles.module.scss';

export interface Props extends React.PropsWithChildren {
    className?: string;
    language?: string;
}

export const Code: React.FC<Props> = ({ children, className, language }) => {
    return (
        <div
            className={classNames(styles.code, className)}
            data-language={language} // Optional: for styling or debugging
        >
            <Box variant="code" color="text-status-inactive">
                {children}
            </Box>
        </div>
    );
};
