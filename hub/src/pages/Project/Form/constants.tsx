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
    ),

    /*footer: (
        <>
            <h3>Learn more</h3>

            <ul>
                <li>
                    <a href="https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/GettingStarted.html">
                        Getting started
                    </a>
                </li>
                <li>
                    <a href="https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/HowCloudFrontWorks.html">
                        How CloudFront delivers content to your users
                    </a>
                </li>
                <li>
                    <a href="https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/distribution-working-with.html">
                        Working with distributions
                    </a>
                </li>
            </ul>
        </>
    ),*/
};
