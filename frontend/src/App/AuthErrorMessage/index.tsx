import React, { PropsWithChildren } from 'react';

import { Box, SpaceBetween } from 'components';

import styles from './styles.module.scss';

export interface Props extends PropsWithChildren {
    title: string;
    text?: string;
}

export const AuthErrorMessage: React.FC<Props> = ({ title, text, children }) => {
    return (
        <Box margin={{ vertical: 'xxxl' }} textAlign="center" color="inherit">
            <SpaceBetween size="xxs">
                <div>
                    <b>{title}</b>

                    {text && (
                        <Box variant="p" color="inherit">
                            {text}
                        </Box>
                    )}
                </div>
            </SpaceBetween>

            <div className={styles.content}>{children}</div>
        </Box>
    );
};
