import React from 'react';
import classNames from 'classnames';
import Box, { BoxProps } from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';

import styles from './styles.module.scss';

export interface Props {
    className?: string;
    padding?: BoxProps['padding'];
}

export const Loader: React.FC<Props> = ({ className, padding = { vertical: 'xxxl' } }) => {
    return (
        <div className={classNames(styles.loader, className)}>
            <Box padding={padding} textAlign="center" color="inherit">
                <SpaceBetween size="m" direction="horizontal">
                    <Spinner />

                    <Box color="inherit">Loading</Box>
                </SpaceBetween>
            </Box>
        </div>
    );
};
