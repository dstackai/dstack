import React from 'react';

export const PROJECT_NAME_HELP = {
    header: <h2>Project name</h2>,
    body: (
        <>
            <p>
                When you create an Amazon CloudFront distribution, you tell CloudFront where to find your content by specifying
                your <i>origin servers</i>. An origin stores the original version of your objects (your files). For example, you
                can specify an Amazon S3 bucket, an AWS Elemental MediaStore container, or an AWS Elemental MediaPackage
                channel. You can also specify a <i>custom origin</i>, such as an Amazon EC2 instance or your own HTTP web
                server.
            </p>
            <p>
                When CloudFront receives requests for your content, it gets the content from the origin and distributes it
                through a worldwide network of data centers called <i>edge locations</i>. CloudFront uses the edge locations
                that are closest to your viewers, so that your content is delivered with the lowest latency and best possible
                performance.
            </p>
            <p>After you create the distribution, you can add more origins to it.</p>
        </>
    ),

    footer: (
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
    ),
};
