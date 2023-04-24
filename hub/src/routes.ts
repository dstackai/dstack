import { buildRoute } from './libs';

export const ROUTES = {
    BASE: '/',
    LOGOUT: '/logout',

    PROJECT: {
        LIST: '/projects',
        ADD: '/projects/add',
        DETAILS: {
            TEMPLATE: `/projects/:name`,
            FORMAT: (name: string) => buildRoute(ROUTES.PROJECT.DETAILS.TEMPLATE, { name }),
            REPOSITORIES: {
                TEMPLATE: `/projects/:name/repositories`,
                FORMAT: (name: string) => buildRoute(ROUTES.PROJECT.DETAILS.REPOSITORIES.TEMPLATE, { name }),
                DETAILS: {
                    TEMPLATE: `/projects/:name/repositories/:repoName`,
                    FORMAT: (name: string, repoName: string) =>
                        buildRoute(ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.TEMPLATE, { name, repoName }),
                },
            },
            RUNS: {
                DETAILS: {
                    TEMPLATE: `/projects/:name/repositories/:repoName/runs/:runName`,
                    FORMAT: (name: string, repoName: string, runName: string) =>
                        buildRoute(ROUTES.PROJECT.DETAILS.RUNS.DETAILS.TEMPLATE, { name, repoName, runName }),
                },
            },
            SETTINGS: {
                TEMPLATE: `/projects/:name/settings`,
                FORMAT: (name: string) => buildRoute(ROUTES.PROJECT.DETAILS.SETTINGS.TEMPLATE, { name }),
            },
        },
        EDIT_BACKEND: {
            TEMPLATE: `/projects/:name/edit/backend`,
            FORMAT: (name: string) => buildRoute(ROUTES.PROJECT.EDIT_BACKEND.TEMPLATE, { name }),
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
