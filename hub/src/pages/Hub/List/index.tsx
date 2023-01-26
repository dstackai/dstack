import React from 'react';
import { Box, Spinner, SpaceBetween } from 'components';
import { useGetHubsQuery } from 'services/hub';

export const HubList: React.FC = () => {
    const { isLoading, data } = useGetHubsQuery();

    if (isLoading)
        return (
            <SpaceBetween size="m" direction="horizontal">
                <Spinner />
                <Box variant="span" color="inherit">
                    Loading
                </Box>
            </SpaceBetween>
        );

    return <Box variant="h1">Hub list: {data?.length} hubs</Box>;
};
