import React from 'react';
import { createBrowserRouter } from 'react-router-dom';
import { Navigate } from 'react-router-dom';
import App from 'App';
import { Logout } from 'App/Logout';
import { HubList, HubDetails, HubEdit, HubAdd } from 'pages/Hub';
import { UserList, UserDetails, UserEdit, UserAdd } from 'pages/User';
import { ROUTES } from './routes';
import { AuthErrorMessage } from './App/AuthErrorMessage';

export const router = createBrowserRouter([
    {
        path: '/',
        element: <App />,
        errorElement: <AuthErrorMessage title="Not Found" text="Page not found" />,
        children: [
            // hubs
            {
                path: ROUTES.BASE,
                element: <Navigate replace to={ROUTES.HUB.LIST} />,
            },
            {
                path: ROUTES.HUB.LIST,
                element: <HubList />,
            },
            {
                path: ROUTES.HUB.DETAILS.TEMPLATE,
                element: <HubDetails />,
            },
            {
                path: ROUTES.HUB.EDIT.TEMPLATE,
                element: <HubEdit />,
            },
            {
                path: ROUTES.HUB.ADD,
                element: <HubAdd />,
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
