import React from 'react';
import { Navigate } from 'react-router-dom';

import AuthLayout from 'layouts/AuthLayout';
import AppLayout from 'layouts/AppLayout';
import Landing from 'pages/Landing';
import WorkflowList from 'pages/Workflow/List';
import WorkflowDetails from 'pages/Workflow/Details';

// auth
import SignIn from 'pages/auth/SignIn';
import SignUp from 'pages/auth/SignUp';
import PasswordSignUp from 'pages/auth/PasswordSignUp';
import CreateSession from 'pages/auth/CreateSession';

import UserDetails from 'pages/Users/Details';

import RepoDetails from 'pages/Repositories/Details';

// settings
import Settings from 'pages/Settings';
import AccountSettings from 'pages/Settings/Account';
import AwsSettings from 'pages/Settings/Clouds';
import GitSettings from 'pages/Settings/Git';
import SecretsSettings from 'pages/Settings/Secrets';

import { getPathParamForRouter } from './url-params';
import { Route } from './types';

const isOnLanding = process.env.LANDING === 'on';
const githubEnabled = process.env.GITHUB_ENABLED;

const runsRoutes: Route[] = [
    {
        name: 'repo',
        element: <RepoDetails />,
        children: [{ name: 'runs', index: true, element: <WorkflowList /> }],
    },
    {
        name: 'run',
        path: `runs/${getPathParamForRouter('RUN_NAME')}`,
        element: <WorkflowDetails />,
    },
    {
        name: 'workflow',
        path: `runs/${getPathParamForRouter('RUN_NAME')}/${getPathParamForRouter('WORKFLOW_NAME')}`,
        element: <WorkflowDetails />,
    },
];

export const index: Route[] = [
    {
        ...(isOnLanding
            ? {
                  name: 'landing',
                  path: '/',
                  element: <Landing />,
              }
            : {}),
    },
    {
        name: 'auth',
        path: '/',
        element: <AuthLayout />,
        children: [
            {
                ...(isOnLanding
                    ? {
                          name: 'login',
                          path: 'login',
                          element: <SignIn />,
                      }
                    : {
                          name: 'login',
                          index: true,
                          element: <SignIn />,
                      }),
            },

            {
                name: 'signup',
                path: 'signup',
                element: githubEnabled ? <SignUp /> : <PasswordSignUp />,
            },

            {
                ...(githubEnabled
                    ? {
                          name: 'signup-email',
                          path: 'signup/email',
                          element: <SignIn />,
                      }
                    : {}),
            },

            {
                name: 'create-session',
                path: 'create-session',
                element: <CreateSession />,
            },
        ],
    },
    {
        name: 'app',
        path: '/',
        element: <AppLayout />,
        children: [
            {
                name: 'user',
                path: getPathParamForRouter('USER_NAME'),
                element: <UserDetails />,
            },
            {
                name: 'user-repo',
                path: `${getPathParamForRouter('USER_NAME')}/${getPathParamForRouter('REPO_NAME')}`,
                children: [...runsRoutes],
            },
            {
                name: 'user-repouser-repo',
                path: `${getPathParamForRouter('USER_NAME')}/${getPathParamForRouter('REPO_USER_NAME')}/${getPathParamForRouter(
                    'REPO_NAME',
                )}`,
                children: [...runsRoutes],
            },
            {
                name: 'settings',
                path: 'settings',
                element: <Settings />,
                children: [
                    {
                        index: true,
                        element: <Navigate to="account" />,
                    },
                    {
                        name: 'account',
                        path: 'account',
                        element: <AccountSettings />,
                    },
                    {
                        name: 'clouds',
                        path: 'clouds',
                        element: <AwsSettings />,
                    },
                    {
                        name: 'git',
                        path: 'git',
                        element: <GitSettings />,
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
