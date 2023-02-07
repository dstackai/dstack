import React from 'react';
import { createBrowserRouter } from 'react-router-dom';
import { Navigate } from 'react-router-dom';
import App from 'App';
import { HubList } from 'pages/Hub';
import { Logout } from 'App/Logout';
import { UserList, UserDetails } from 'pages/User';
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
            // members
            {
                path: ROUTES.USER.LIST,
                element: <UserList />,
            },
            {
                path: ROUTES.USER.DETAILS.TEMPLATE,
                element: <UserDetails />,
            },

            // auth
            {
                path: ROUTES.LOGOUT,
                element: <Logout />,
            },
        ],
    },
]);
