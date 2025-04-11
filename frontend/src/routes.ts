import { buildRoute } from './libs';

export const ROUTES = {
    BASE: '/',
    LOGOUT: '/logout',

    AUTH: {
        GITHUB_CALLBACK: `/auth/github/callback`,
        OKTA_CALLBACK: `/auth/okta/callback`,
        ENTRA_CALLBACK: `/auth/entra/callback`,
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
                    TEMPLATE: `/projects/:projectName/runs/:runId`,
                    FORMAT: (projectName: string, runId: string) =>
                        buildRoute(ROUTES.PROJECT.DETAILS.RUNS.DETAILS.TEMPLATE, { projectName, runId }),
                    METRICS: {
                        TEMPLATE: `/projects/:projectName/runs/:runId/metrics`,
                        FORMAT: (projectName: string, runId: string) =>
                            buildRoute(ROUTES.PROJECT.DETAILS.RUNS.DETAILS.METRICS.TEMPLATE, { projectName, runId }),
                    },
                    JOBS: {
                        DETAILS: {
                            TEMPLATE: `/projects/:projectName/runs/:runId/jobs/:jobName`,
                            FORMAT: (projectName: string, runId: string, jobName: string) =>
                                buildRoute(ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.TEMPLATE, {
                                    projectName,
                                    runId,
                                    jobName,
                                }),
                            METRICS: {
                                TEMPLATE: `/projects/:projectName/runs/:runId/jobs/:jobName/metrics`,
                                FORMAT: (projectName: string, runId: string, jobName: string) =>
                                    buildRoute(ROUTES.PROJECT.DETAILS.RUNS.DETAILS.JOBS.DETAILS.METRICS.TEMPLATE, {
                                        projectName,
                                        runId,
                                        jobName,
                                    }),
                            },
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
            TEMPLATE: `/projects/:projectName/fleets/:fleetId`,
            FORMAT: (projectName: string, fleetId: string) =>
                buildRoute(ROUTES.FLEETS.DETAILS.TEMPLATE, { projectName, fleetId }),
        },
    },

    INSTANCES: {
        LIST: '/instances',
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
        PROJECTS: {
            TEMPLATE: `/users/:userName/projects`,
            FORMAT: (userName: string) => buildRoute(ROUTES.USER.PROJECTS.TEMPLATE, { userName }),
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
