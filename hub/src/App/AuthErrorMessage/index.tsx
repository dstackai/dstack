import React from 'react';
import { Box, SpaceBetween } from 'components';

export interface Props {
    title: string;
    text: string;
}

export const AuthErrorMessage: React.FC<Props> = ({ title, text }) => {
    return (
        <Box margin={{ vertical: 'xxxl' }} textAlign="center" color="inherit">
            <SpaceBetween size="xxs">
                <div>
                    <b>{title}</b>
                    <Box variant="p" color="inherit">
                        {text}
                    </Box>
                </div>
            </SpaceBetween>
        </Box>
    );
};
