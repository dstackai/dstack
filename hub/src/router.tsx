import React from 'react';
import { createBrowserRouter } from 'react-router-dom';
import { Navigate } from 'react-router-dom';
import App from 'App';
import { Logout } from 'App/Logout';
import { HubList, HubDetails, HubEditBackend, HubAdd } from 'pages/Hub';
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
                element: <Navigate replace to={ROUTES.PROJECT.LIST} />,
            },
            {
                path: ROUTES.PROJECT.LIST,
                element: <HubList />,
            },
            {
                path: ROUTES.PROJECT.DETAILS.TEMPLATE,
                element: <HubDetails />,
            },
            {
                path: ROUTES.PROJECT.EDIT_BACKEND.TEMPLATE,
                element: <HubEditBackend />,
            },
            {
                path: ROUTES.PROJECT.ADD,
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
