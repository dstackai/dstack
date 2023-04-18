import React from 'react';
import Box from '@cloudscape-design/components/box';

import { IProps } from './types';

export const ListEmptyMessage: React.FC<IProps> = ({ title, message, children }) => {
    return (
        <Box textAlign="center" color="inherit">
            {title && <b>{title}</b>}
            <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                {message}
            </Box>
            {children}
        </Box>
    );
};
