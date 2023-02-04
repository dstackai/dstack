import { buildRoute } from './libs';

export const ROUTES = {
    BASE: '/',
    LOGOUT: '/logout',

    HUB: {
        LIST: '/hubs',
        DETAILS: {
            TEMPLATE: `/hubs/:name`,
            FORMAT: (name: string) => buildRoute(ROUTES.HUB.DETAILS.TEMPLATE, { name }),
        },
    },

    MEMBER: {
        LIST: '/members',
        DETAILS: {
            TEMPLATE: `/members/:name`,
            FORMAT: (name: string) => buildRoute(ROUTES.MEMBER.DETAILS.TEMPLATE, { name }),
        },
    },
};
