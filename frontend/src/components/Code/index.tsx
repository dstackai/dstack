import React, { forwardRef } from 'react';
import classNames from 'classnames';
import Box from '@cloudscape-design/components/box';

import styles from './styles.module.scss';

export interface Props extends React.PropsWithChildren {
    className?: string;
}

export const Code = forwardRef<HTMLDivElement, Props>(({ children, className }, ref) => {
    return (
        <div ref={ref} className={classNames(styles.code, className)}>
            <Box variant="code" color="text-status-inactive">
                {children}
            </Box>
        </div>
    );
});
