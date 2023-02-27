import React from 'react';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';

import styles from './styles.module.scss';

export interface Props {
    className?: string;
}

export const Loader: React.FC<Props> = () => {
    return (
        <div className={styles.loader}>
            <Box padding={{ vertical: 'xxxl' }} textAlign="center" color="inherit">
                <SpaceBetween size="m" direction="horizontal">
                    <Spinner />

                    <Box color="inherit">Loading</Box>
                </SpaceBetween>
            </Box>
        </div>
    );
};
