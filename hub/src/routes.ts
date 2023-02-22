import { buildRoute } from './libs';

export const ROUTES = {
    BASE: '/',
    LOGOUT: '/logout',

    HUB: {
        LIST: '/hubs',
        ADD: '/hubs/add',
        DETAILS: {
            TEMPLATE: `/hubs/:name`,
            FORMAT: (name: string) => buildRoute(ROUTES.HUB.DETAILS.TEMPLATE, { name }),
        },
        EDIT_BACKEND: {
            TEMPLATE: `/hubs/:name/edit/backend`,
            FORMAT: (name: string) => buildRoute(ROUTES.HUB.EDIT_BACKEND.TEMPLATE, { name }),
        },
    },

    USER: {
        LIST: '/users',
        ADD: '/users/add',
        DETAILS: {
            TEMPLATE: `/users/:name`,
            FORMAT: (name: string) => buildRoute(ROUTES.USER.DETAILS.TEMPLATE, { name }),
        },
        EDIT: {
            TEMPLATE: `/users/:name/edit`,
            FORMAT: (name: string) => buildRoute(ROUTES.USER.EDIT.TEMPLATE, { name }),
        },
    },
};
