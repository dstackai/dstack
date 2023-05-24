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
            SETTINGS: {
                TEMPLATE: `/projects/:name/settings`,
                FORMAT: (name: string) => buildRoute(ROUTES.PROJECT.DETAILS.SETTINGS.TEMPLATE, { name }),
            },

            REPOSITORIES: {
                TEMPLATE: `/projects/:name/repositories`,
                FORMAT: (name: string) => buildRoute(ROUTES.PROJECT.DETAILS.REPOSITORIES.TEMPLATE, { name }),
                DETAILS: {
                    TEMPLATE: `/projects/:name/repositories/:repoId`,
                    FORMAT: (name: string, repoId: string) =>
                        buildRoute(ROUTES.PROJECT.DETAILS.REPOSITORIES.DETAILS.TEMPLATE, { name, repoId }),
                },
            },

            RUNS: {
                DETAILS: {
                    TEMPLATE: `/projects/:name/repositories/:repoId/runs/:runName`,
                    FORMAT: (name: string, repoId: string, runName: string) =>
                        buildRoute(ROUTES.PROJECT.DETAILS.RUNS.DETAILS.TEMPLATE, { name, repoId, runName }),
                },
                ARTIFACTS: {
                    TEMPLATE: `/projects/:name/repositories/:repoId/runs/:runName/artifacts`,
                    FORMAT: (name: string, repoId: string, runName: string) =>
                        buildRoute(ROUTES.PROJECT.DETAILS.RUNS.ARTIFACTS.TEMPLATE, { name, repoId, runName }),
                },
            },

            TAGS: {
                TEMPLATE: `/projects/:name/repositories/:repoId/tags`,
                FORMAT: (name: string, repoId: string) => buildRoute(ROUTES.PROJECT.DETAILS.TAGS.TEMPLATE, { name, repoId }),

                DETAILS: {
                    TEMPLATE: `/projects/:name/repositories/:repoId/tags/:tagName`,
                    FORMAT: (name: string, repoId: string, tagName: string) =>
                        buildRoute(ROUTES.PROJECT.DETAILS.TAGS.DETAILS.TEMPLATE, { name, repoId, tagName }),
                },
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
