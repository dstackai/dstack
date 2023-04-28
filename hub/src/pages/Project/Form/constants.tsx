import React from 'react';

export const BACKEND_TYPE_HELP = {
    header: <h2>Backend type</h2>,
    body: (
        <>
            <p>
                The <i>Backend type</i> defines where to run workflows and store artifacts.
            </p>
            <p>
                If you choose to run workflows in the cloud, <i>dstack Hub</i> will automatically create the necessary cloud
                resources at the workflow startup and tear them down once it is finished.
            </p>
        </>
    )
};
