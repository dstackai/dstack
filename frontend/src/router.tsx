import React from 'react';
import type { RouteObject } from 'react-router-dom';
import { createBrowserRouter } from 'react-router-dom';
import { Navigate } from 'react-router-dom';

import App from 'App';
import { LoginByEntraIDCallback } from 'App/Login/EntraID/LoginByEntraIDCallback';
import { LoginByGithubCallback } from 'App/Login/LoginByGithubCallback';
import { LoginByGoogleCallback } from 'App/Login/LoginByGoogleCallback';
import { LoginByOktaCallback } from 'App/Login/LoginByOktaCallback';
import { TokenLogin } from 'App/Login/TokenLogin';
import { Logout } from 'App/Logout';
import { FleetDetails, FleetList } from 'pages/Fleets';
import { EventsList as FleetEventsList } from 'pages/Fleets/Details/Events';
import { FleetDetails as FleetDetailsGeneral } from 'pages/Fleets/Details/FleetDetails';
import { InstanceList } from 'pages/Instances';
import { ModelsList } from 'pages/Models';
import { ModelDetails } from 'pages/Models/Details';
import { CreateProjectWizard, ProjectAdd, ProjectDetails, ProjectList, ProjectSettings } from 'pages/Project';
import { BackendAdd, BackendEdit } from 'pages/Project/Backends';
import { AddGateway, EditGateway } from 'pages/Project/Gateways';
import {
    CreateDevEnvironment,
    EventsList as RunEvents,
    JobLogs,
    JobMetrics,
    RunDetails,
    RunDetailsPage,
    RunList,
} from 'pages/Runs';
import { JobDetailsPage } from 'pages/Runs/Details/Jobs/Details';
import { EventsList as JobEvents } from 'pages/Runs/Details/Jobs/Events';
import { CreditsHistoryAdd, UserAdd, UserDetails, UserEdit, UserList } from 'pages/User';
import { UserBilling, UserProjects, UserSettings } from 'pages/User/Details';

import { AuthErrorMessage } from './App/AuthErrorMessage';
import { EventList } from './pages/Events';
import { OfferList } from './pages/Offers';
import { JobDetails } from './pages/Runs/Details/Jobs/Details/JobDetails';
import { VolumeList } from './pages/Volumes';
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
                path: ROUTES.AUTH.OKTA_CALLBACK,
                element: <LoginByOktaCallback />,
            },
            {
                path: ROUTES.AUTH.ENTRA_CALLBACK,
                element: <LoginByEntraIDCallback />,
            },
            {
                path: ROUTES.AUTH.GOOGLE_CALLBACK,
                element: <LoginByGoogleCallback />,
            },
            {
                path: ROUTES.AUTH.TOKEN,
                element: <TokenLogin />,
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
                        index: true,
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
                ],
            },
            {
                path: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.TEMPLATE,
                element: <RunDetailsPage />,
                children: [
                    {
                        index: true,
                        element: <RunDetails />,
                    },
                    {
                        path: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.METRICS.TEMPLATE,
                        element: <JobMetrics />,
                    },
                    {
                        path: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.LOGS.TEMPLATE,
                        element: <JobLogs />,
                    },
                    {
                        path: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.EVENTS.TEMPLATE,
                        element: <RunEvents />,
                    },
                ],
            },
            {
                path: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.TEMPLATE,
                element: <JobDetailsPage />,
                children: [
                    {
                        index: true,
                        element: <JobDetails />,
                    },
                    {
                        path: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.METRICS.TEMPLATE,
                        element: <JobMetrics />,
                    },
                    {
                        path: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.LOGS.TEMPLATE,
                        element: <JobLogs />,
                    },
                    {
                        path: ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.EVENTS.TEMPLATE,
                        element: <JobEvents />,
                    },
                ],
            },

            ...([
                process.env.UI_VERSION !== 'sky' && {
                    path: ROUTES.PROJECT.ADD,
                    element: <ProjectAdd />,
                },
                process.env.UI_VERSION === 'sky' && {
                    path: ROUTES.PROJECT.ADD,
                    element: <CreateProjectWizard />,
                },
            ].filter(Boolean) as RouteObject[]),

            // Runs
            {
                path: ROUTES.RUNS.LIST,
                element: <RunList />,
            },

            {
                path: ROUTES.RUNS.CREATE_DEV_ENV,
                element: <CreateDevEnvironment />,
            },

            // Offers
            {
                path: ROUTES.OFFERS.LIST,
                element: <OfferList />,
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

            // Events
            {
                path: ROUTES.EVENTS.LIST,
                element: <EventList />,
            },

            // Fleets
            {
                path: ROUTES.FLEETS.LIST,
                element: <FleetList />,
            },
            {
                path: ROUTES.FLEETS.DETAILS.TEMPLATE,
                element: <FleetDetails />,
                children: [
                    {
                        index: true,
                        element: <FleetDetailsGeneral />,
                    },
                    {
                        path: ROUTES.FLEETS.DETAILS.EVENTS.TEMPLATE,
                        element: <FleetEventsList />,
                    },
                ],
            },

            // Instances
            {
                path: ROUTES.INSTANCES.LIST,
                element: <InstanceList />,
            },

            // Volumes
            {
                path: ROUTES.VOLUMES.LIST,
                element: <VolumeList />,
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
                    {
                        path: ROUTES.USER.PROJECTS.TEMPLATE,
                        element: <UserProjects />,
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
