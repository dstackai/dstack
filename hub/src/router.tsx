import React from 'react';
import { createBrowserRouter } from 'react-router-dom';
import { Navigate } from 'react-router-dom';

import App from 'App';
import { Logout } from 'App/Logout';
import { ProjectAdd, ProjectDetails, ProjectEditBackend, ProjectList, ProjectSettings } from 'pages/Project';
import { RepositoryDetails, RepositoryList, RepositorySettings } from 'pages/Repositories';
import { Artifacts as RunArtifacts, Logs as RunLogs, RunDetails, RunList } from 'pages/Runs';
import { TagDetails, TagList } from 'pages/Tags';
import { UserAdd, UserDetails, UserEdit, UserList } from 'pages/User';

import { AuthErrorMessage } from './App/AuthErrorMessage';
import { ROUTES } from './routes';

export const router = createBrowserRouter([
    {
        path: '/',
        element: <App />,
        errorElement: <AuthErrorMessage title="Not Found" text="Page not found" />,
        children: [
            // hubs
            {
                path: ROUTES.BASE,
                element: <Navigate replace to={ROUTES.PROJECT.LIST} />,
            },
            {
                path: ROUTES.PROJECT.LIST,
                element: <ProjectList />,
            },
            {
                path: ROUTES.PROJECT.DETAILS.TEMPLATE,
                element: <ProjectDetails />,
                children: [
                    {
                        path: ROUTES.PROJECT.DETAILS.REPOSITORIES.TEMPLATE,
                        element: <RepositoryList />,
                    },
                    {
                        path: ROUTES.PROJECT.DETAILS.SETTINGS.TEMPLATE,
                        element: <ProjectSettings />,
                    },
                ],
            },
            {
                path: ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.TEMPLATE,
                element: <RepositoryDetails />,

                children: [
                    {
                        index: true,
                        element: <RunList />,
                    },
                    {
                        path: ROUTES.PROJECT.DETAILS.TAGS.TEMPLATE,
                        element: <TagList />,
                    },
                ],
            },
            {
                path: ROUTES.PROJECT.DETAILS.REPOSITORIES.SETTINGS.TEMPLATE,
                element: <RepositorySettings />,
            },
            {
                path: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.TEMPLATE,
                element: <RunDetails />,

                children: [
                    {
                        index: true,
                        element: <RunLogs />,
                    },

                    {
                        path: ROUTES.PROJECT.DETAILS.RUNS.ARTIFACTS.TEMPLATE,
                        element: <RunArtifacts />,
                    },
                ],
            },
            {
                path: ROUTES.PROJECT.DETAILS.TAGS.DETAILS.TEMPLATE,
                element: <TagDetails />,

                children: [
                    // {
                    //     index: true,
                    //     element: <RunLogs />,
                    // },
                ],
            },

            {
                path: ROUTES.PROJECT.EDIT_BACKEND.TEMPLATE,
                element: <ProjectEditBackend />,
            },
            {
                path: ROUTES.PROJECT.ADD,
                element: <ProjectAdd />,
            },
            // members
            {
                path: ROUTES.USER.LIST,
                element: <UserList />,
            },
            {
                path: ROUTES.USER.ADD,
                element: <UserAdd />,
            },
            {
                path: ROUTES.USER.DETAILS.TEMPLATE,
                element: <UserDetails />,
            },
            {
                path: ROUTES.USER.EDIT.TEMPLATE,
                element: <UserEdit />,
            },

            // auth
            {
                path: ROUTES.LOGOUT,
                element: <Logout />,
            },
        ],
    },
]);
