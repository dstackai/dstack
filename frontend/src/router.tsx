import React from 'react';
import type { RouteObject } from 'react-router-dom';
import { createBrowserRouter } from 'react-router-dom';
import { Navigate } from 'react-router-dom';

import App from 'App';
import { LoginByGithubCallback } from 'App/Login/LoginByGithubCallback';
import { LoginByTokenForm } from 'App/Login/LoginByTokenForm';
import { Logout } from 'App/Logout';
import { AdministrationFleetsList, FleetDetails, FleetsList } from 'pages/Fleets';
import { ModelsList } from 'pages/Models';
import { ModelDetails } from 'pages/Models/Details';
import { ProjectAdd, ProjectDetails, ProjectList, ProjectSettings } from 'pages/Project';
import { BackendAdd, BackendEdit } from 'pages/Project/Backends';
import { AddGateway, EditGateway } from 'pages/Project/Gateways';
import { AdministrationList, List as MainRunList, Logs as RunLogs, RunDetails } from 'pages/Runs';
import { CreditsHistoryAdd, UserAdd, UserDetails, UserEdit, UserList } from 'pages/User';
import { UserBilling, UserSettings } from 'pages/User/Details';

import { AuthErrorMessage } from './App/AuthErrorMessage';
import { AdministrationVolumeList, VolumeList } from './pages/Volumes';
import { ROUTES } from './routes';

export const router = createBrowserRouter([
    {
        path: '/',
        element: <App />,
        errorElement: <AuthErrorMessage title="Not Found" text="Page not found" />,
        children: [
            // auth
            {
                path: ROUTES.AUTH.GITHUB_CALLBACK,
                element: <LoginByGithubCallback />,
            },
            {
                path: ROUTES.AUTH.TOKEN,
                element: <LoginByTokenForm />,
            },
            // hubs
            {
                path: ROUTES.BASE,
                element: <Navigate replace to={ROUTES.RUNS.LIST} />,
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
                        path: ROUTES.PROJECT.DETAILS.SETTINGS.TEMPLATE,
                        element: <ProjectSettings />,
                    },

                    {
                        path: ROUTES.PROJECT.BACKEND.ADD.TEMPLATE,
                        element: <BackendAdd />,
                    },

                    {
                        path: ROUTES.PROJECT.BACKEND.EDIT.TEMPLATE,
                        element: <BackendEdit />,
                    },

                    {
                        path: ROUTES.PROJECT.GATEWAY.ADD.TEMPLATE,
                        element: <AddGateway />,
                    },

                    {
                        path: ROUTES.PROJECT.GATEWAY.EDIT.TEMPLATE,
                        element: <EditGateway />,
                    },
                ].filter(Boolean),
            },
            {
                path: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.TEMPLATE,
                element: <RunDetails />,

                children: [
                    {
                        index: true,
                        element: <RunLogs />,
                    },
                ],
            },

            {
                path: ROUTES.PROJECT.ADD,
                element: <ProjectAdd />,
            },

            // Runs
            {
                path: ROUTES.RUNS.LIST,
                element: <MainRunList />,
            },

            // Models
            {
                path: ROUTES.MODELS.LIST,
                element: <ModelsList />,
            },
            {
                path: ROUTES.MODELS.DETAILS.TEMPLATE,
                element: <ModelDetails />,
            },

            // Fleets
            {
                path: ROUTES.FLEETS.LIST,
                element: <FleetsList />,
            },
            {
                path: ROUTES.FLEETS.DETAILS.TEMPLATE,
                element: <FleetDetails />,
            },

            // Volumes
            {
                path: ROUTES.VOLUMES.LIST,
                element: <VolumeList />,
            },

            // administration
            {
                path: ROUTES.ADMINISTRATION.RUNS.LIST,
                element: <AdministrationList />,
            },
            {
                path: ROUTES.ADMINISTRATION.FLEETS.LIST,
                element: <AdministrationFleetsList />,
            },
            {
                path: ROUTES.ADMINISTRATION.VOLUMES.LIST,
                element: <AdministrationVolumeList />,
            },

            // Users
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
                children: [
                    {
                        index: true,
                        element: <UserSettings />,
                    },
                    process.env.UI_VERSION === 'sky' && {
                        path: ROUTES.USER.BILLING.LIST.TEMPLATE,
                        element: <UserBilling />,
                    },
                ].filter(Boolean) as RouteObject[],
            },
            {
                path: ROUTES.USER.EDIT.TEMPLATE,
                element: <UserEdit />,
            },
            {
                path: ROUTES.USER.BILLING.ADD_PAYMENT.TEMPLATE,
                element: <CreditsHistoryAdd />,
            },

            // auth
            {
                path: ROUTES.LOGOUT,
                element: <Logout />,
            },
        ],
    },
]);
