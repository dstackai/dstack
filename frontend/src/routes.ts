import { buildRoute } from './libs';

export const ROUTES = {
    BASE: '/',
    LOGOUT: '/logout',

    AUTH: {
        GITHUB_CALLBACK: `/auth/github/callback`,
        OKTA_CALLBACK: `/auth/okta/callback`,
        TOKEN: `/auth/token`,
    },

    PROJECT: {
        LIST: '/projects',
        ADD: '/projects/add',
        DETAILS: {
            TEMPLATE: `/projects/:projectName`,
            FORMAT: (projectName: string) => buildRoute(ROUTES.PROJECT.DETAILS.TEMPLATE, { projectName }),
            SETTINGS: {
                TEMPLATE: `/projects/:projectName`,
                FORMAT: (projectName: string) => buildRoute(ROUTES.PROJECT.DETAILS.SETTINGS.TEMPLATE, { projectName }),
            },

            RUNS: {
                DETAILS: {
                    TEMPLATE: `/projects/:projectName/runs/:runName`,
                    FORMAT: (projectName: string, runName: string) =>
                        buildRoute(ROUTES.PROJECT.DETAILS.RUNS.DETAILS.TEMPLATE, { projectName, runName }),
                    JOBS: {
                        DETAILS: {
                            TEMPLATE: `/projects/:projectName/runs/:runName/jobs/:jobName`,
                            FORMAT: (projectName: string, runName: string, jobName: string) =>
                                buildRoute(ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.TEMPLATE, {
                                    projectName,
                                    runName,
                                    jobName,
                                }),
                        },
                    },
                },
            },
        },
        BACKEND: {
            ADD: {
                TEMPLATE: `/projects/:projectName/backends/add`,
                FORMAT: (projectName: string) => buildRoute(ROUTES.PROJECT.BACKEND.ADD.TEMPLATE, { projectName }),
            },
            EDIT: {
                TEMPLATE: `/projects/:projectName/backends/:backend`,
                FORMAT: (projectName: string, backendName: string) =>
                    buildRoute(ROUTES.PROJECT.BACKEND.EDIT.TEMPLATE, { projectName, backend: backendName }),
            },
        },
        GATEWAY: {
            ADD: {
                TEMPLATE: `/projects/:projectName/gateways/add`,
                FORMAT: (projectName: string) => buildRoute(ROUTES.PROJECT.GATEWAY.ADD.TEMPLATE, { projectName }),
            },
            EDIT: {
                TEMPLATE: `/projects/:projectName/gateways/:instance`,
                FORMAT: (projectName: string, instanceName: string) =>
                    buildRoute(ROUTES.PROJECT.GATEWAY.EDIT.TEMPLATE, { projectName, instance: instanceName }),
            },
        },
    },

    RUNS: {
        LIST: '/runs',
    },

    MODELS: {
        LIST: '/models',
        DETAILS: {
            TEMPLATE: `/projects/:projectName/models/:runName`,
            FORMAT: (projectName: string, runName: string) =>
                buildRoute(ROUTES.MODELS.DETAILS.TEMPLATE, { projectName, runName }),
        },
    },

    FLEETS: {
        LIST: '/fleets',
        DETAILS: {
            TEMPLATE: `/projects/:projectName/fleets/:fleetName`,
            FORMAT: (projectName: string, fleetName: string) =>
                buildRoute(ROUTES.FLEETS.DETAILS.TEMPLATE, { projectName, fleetName }),
        },
    },

    VOLUMES: {
        LIST: '/volumes',
    },

    USER: {
        LIST: '/users',
        ADD: '/users/add',
        DETAILS: {
            TEMPLATE: `/users/:userName`,
            FORMAT: (userName: string) => buildRoute(ROUTES.USER.DETAILS.TEMPLATE, { userName }),
        },
        EDIT: {
            TEMPLATE: `/users/:userName/edit`,
            FORMAT: (userName: string) => buildRoute(ROUTES.USER.EDIT.TEMPLATE, { userName }),
        },
        BILLING: {
            LIST: {
                TEMPLATE: `/users/:userName/billing`,
                FORMAT: (userName: string) => buildRoute(ROUTES.USER.BILLING.LIST.TEMPLATE, { userName }),
            },
            ADD_PAYMENT: {
                TEMPLATE: `/users/:userName/billing/payments/add`,
                FORMAT: (userName: string) => buildRoute(ROUTES.USER.BILLING.ADD_PAYMENT.TEMPLATE, { userName }),
            },
        },
    },

    BILLING: {
        BALANCE: '/billing',
    },
};
