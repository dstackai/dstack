import React from 'react';
import { createBrowserRouter } from 'react-router-dom';
import { Navigate } from 'react-router-dom';
import App from 'App';
import { HubList } from 'pages/Hub';
import { Logout } from 'App/Logout';
import { MemberList, MemberDetails } from 'pages/Member';
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
                path: ROUTES.MEMBER.LIST,
                element: <MemberList />,
            },
            {
                path: ROUTES.MEMBER.DETAILS.TEMPLATE,
                element: <MemberDetails />,
            },

            // auth
            {
                path: ROUTES.LOGOUT,
                element: <Logout />,
            },
        ],
    },
]);
