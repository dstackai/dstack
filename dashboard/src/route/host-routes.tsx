import React from 'react';
import { Navigate } from 'react-router-dom';

import AppLayout from 'layouts/AppLayout';

import WorkflowList from 'pages/Workflow/List';
import WorkflowDetails from 'pages/Workflow/Details';

import UserDetails from 'pages/Users/Details';

import RepoDetails from 'pages/Repositories/Details';

import TagList from 'pages/Tag/List';
import TagDetails from 'pages/Tag/Details';

import Settings from 'pages/Settings';
import SecretsSettings from 'pages/Settings/Secrets';

import { getPathParamForRouter } from './url-params';
import { Route } from './types';

const runsRoutes: Route[] = [
    {
        name: 'repo',
        element: <RepoDetails />,
        children: [
            { name: 'runs', index: true, element: <WorkflowList /> },

            {
                name: 'tags',
                path: `tags`,
                element: <TagList />,
            },
        ],
    },

    {
        name: 'run',
        path: `runs/${getPathParamForRouter('RUN_NAME')}`,
        element: <WorkflowDetails />,
    },

    {
        name: 'tag',
        path: `tags/${getPathParamForRouter('TAG_NAME')}`,
        element: <TagDetails />,
    },

    {
        name: 'workflow',
        path: `runs/${getPathParamForRouter('RUN_NAME')}/${getPathParamForRouter('WORKFLOW_NAME')}`,
        element: <WorkflowDetails />,
    },
];

export const hostRoutes: Route[] = [
    {
        name: 'app',
        path: '/',
        element: <AppLayout />,
        children: [
            {
                name: 'user',
                index: true,
                element: <UserDetails />,
            },
            {
                name: 'user-repo',
                path: `${getPathParamForRouter('REPO_NAME')}`,
                children: [...runsRoutes],
            },
            {
                name: 'user-repouser-repo',
                path: `${getPathParamForRouter('REPO_USER_NAME')}/${getPathParamForRouter('REPO_NAME')}`,
                children: [...runsRoutes],
            },
            {
                name: 'settings',
                path: 'settings',
                element: <Settings />,
                children: [
                    {
                        index: true,
                        element: <Navigate to="secrets" />,
                    },
                    {
                        name: 'secrets',
                        path: 'secrets',
                        element: <SecretsSettings />,
                    },
                ],
            },
        ],
    },
];
