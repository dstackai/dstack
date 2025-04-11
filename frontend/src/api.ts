const BASE_URL = process.env.API_URL;

export const API = {
    BASE: () => `${BASE_URL}`,

    AUTH: {
        BASE: () => `${API.BASE()}/auth`,
        GITHUB: {
            BASE: () => `${API.AUTH.BASE()}/github`,
            AUTHORIZE: () => `${API.AUTH.GITHUB.BASE()}/authorize`,
            CALLBACK: () => `${API.AUTH.GITHUB.BASE()}/callback`,
        },
        OKTA: {
            BASE: () => `${API.AUTH.BASE()}/okta`,
            INFO: () => `${API.AUTH.OKTA.BASE()}/info`,
            AUTHORIZE: () => `${API.AUTH.OKTA.BASE()}/authorize`,
            CALLBACK: () => `${API.AUTH.OKTA.BASE()}/callback`,
        },
        ENTRA: {
            BASE: () => `${API.AUTH.BASE()}/entra`,
            INFO: () => `${API.AUTH.ENTRA.BASE()}/info`,
            AUTHORIZE: () => `${API.AUTH.ENTRA.BASE()}/authorize`,
            CALLBACK: () => `${API.AUTH.ENTRA.BASE()}/callback`,
        },
    },

    USERS: {
        BASE: () => `${API.BASE()}/users`,
        LIST: () => `${API.USERS.BASE()}/list`,
        CREATE: () => `${API.USERS.BASE()}/create`,
        UPDATE: () => `${API.USERS.BASE()}/update`,
        DETAILS: () => `${API.USERS.BASE()}/get_user`,
        CURRENT_USER: () => `${API.USERS.BASE()}/get_my_user`,
        REFRESH_TOKEN: () => `${API.USERS.BASE()}/refresh_token`,
        DELETE: () => `${API.USERS.BASE()}/delete`,
    },

    USER_PAYMENTS: {
        BASE: (username: string) => `${API.BASE()}/user/${username}/payments`,
        LIST: (username: string) => `${API.USER_PAYMENTS.BASE(username)}/list`,
        ADD: (username: string) => `${API.USER_PAYMENTS.BASE(username)}/add`,
    },

    USER_BILLING: {
        BASE: (username: string) => `${API.BASE()}/user/${username}/billing`,
        INFO: (username: string) => `${API.USER_BILLING.BASE(username)}/info`,
        CHECKOUT_SESSION: (username: string) => `${API.USER_BILLING.BASE(username)}/checkout_session`,
        PORTAL_SESSION: (username: string) => `${API.USER_BILLING.BASE(username)}/portal_session`,
    },

    PROJECTS: {
        BASE: () => `${API.BASE()}/projects`,
        LIST: () => `${API.PROJECTS.BASE()}/list`,
        CREATE: () => `${API.PROJECTS.BASE()}/create`,
        DELETE: () => `${API.PROJECTS.BASE()}/delete`,
        DETAILS: (name: IProject['project_name']) => `${API.PROJECTS.BASE()}/${name}`,
        DETAILS_INFO: (name: IProject['project_name']) => `${API.PROJECTS.DETAILS(name)}/get`,
        SET_MEMBERS: (name: IProject['project_name']) => `${API.PROJECTS.DETAILS(name)}/set_members`,

        // Repos
        REPOS: (projectName: IProject['project_name']) => `${API.BASE()}/project/${projectName}/repos`,
        REPOS_LIST: (projectName: IProject['project_name']) => `${API.PROJECTS.REPOS(projectName)}/list`,

        // Runs
        RUNS: (projectName: IProject['project_name']) => `${API.BASE()}/project/${projectName}/runs`,
        RUNS_LIST: (projectName: IProject['project_name']) => `${API.PROJECTS.RUNS(projectName)}/list`,
        RUN_DETAILS: (projectName: IProject['project_name']) => `${API.PROJECTS.RUNS(projectName)}/get`,
        RUN_GET_PLAN: (projectName: IProject['project_name']) => `${API.PROJECTS.RUNS(projectName)}/get_plan`,
        RUNS_DELETE: (projectName: IProject['project_name']) => `${API.PROJECTS.RUNS(projectName)}/delete`,
        RUNS_STOP: (projectName: IProject['project_name']) => `${API.PROJECTS.RUNS(projectName)}/stop`,
        RUNS_SUBMIT: (projectName: IProject['project_name']) => `${API.PROJECTS.RUNS(projectName)}/submit`,

        // Logs
        LOGS: (projectName: IProject['project_name']) => `${API.BASE()}/project/${projectName}/logs/poll`,

        // Logs
        ARTIFACTS: (projectName: IProject['project_name']) => `${API.BASE()}/project/${projectName}/artifacts/list`,

        // Fleets
        FLEETS: (projectName: IProject['project_name']) => `${API.BASE()}/project/${projectName}/fleets/list`,
        FLEETS_DETAILS: (projectName: IProject['project_name']) => `${API.BASE()}/project/${projectName}/fleets/get`,
        FLEETS_DELETE: (projectName: IProject['project_name']) => `${API.BASE()}/project/${projectName}/fleets/delete`,
        FLEET_INSTANCES_DELETE: (projectName: IProject['project_name']) =>
            `${API.BASE()}/project/${projectName}/fleets/delete_instances`,

        // Fleets
        VOLUMES_DELETE: (projectName: IProject['project_name']) => `${API.BASE()}/project/${projectName}/volumes/delete`,

        // METRICS
        JOB_METRICS: (projectName: IProject['project_name'], runName: IRun['run_spec']['run_name']) =>
            `${API.BASE()}/project/${projectName}/metrics/job/${runName}`,
    },

    BACKENDS: {
        BASE: () => `${API.BASE()}/backends`,
        LIST_TYPES: () => `${API.BACKENDS.BASE()}/list_types`,
        CONFIG_VALUES: () => `${API.BACKENDS.BASE()}/config_values`,
    },

    PROJECT_BACKENDS: {
        BASE: (projectName: IProject['project_name']) => `${API.BASE()}/project/${projectName}/backends`,
        LIST: (projectName: IProject['project_name']) => `${API.PROJECT_BACKENDS.BASE(projectName)}/list`,
        CREATE: (projectName: IProject['project_name']) => `${API.PROJECT_BACKENDS.BASE(projectName)}/create`,
        UPDATE: (projectName: IProject['project_name']) => `${API.PROJECT_BACKENDS.BASE(projectName)}/update`,
        DELETE: (projectName: IProject['project_name']) => `${API.PROJECT_BACKENDS.BASE(projectName)}/delete`,
        BACKEND_CONFIG_INFO: (projectName: IProject['project_name'], backendName: string) =>
            `${API.PROJECT_BACKENDS.BASE(projectName)}/${backendName}/config_info`,
        CREATE_YAML: (projectName: IProject['project_name']) => `${API.PROJECT_BACKENDS.BASE(projectName)}/create_yaml`,
        UPDATE_YAML: (projectName: IProject['project_name']) => `${API.PROJECT_BACKENDS.BASE(projectName)}/update_yaml`,
        GET_YAML: (projectName: IProject['project_name'], backendName: string) =>
            `${API.PROJECT_BACKENDS.BASE(projectName)}/${backendName}/get_yaml`,
    },

    PROJECT_GATEWAYS: {
        BASE: (projectName: IProject['project_name']) => `${API.BASE()}/project/${projectName}/gateways`,
        LIST: (projectName: IProject['project_name']) => `${API.PROJECT_GATEWAYS.BASE(projectName)}/list`,
        CREATE: (projectName: IProject['project_name']) => `${API.PROJECT_GATEWAYS.BASE(projectName)}/create`,
        DELETE: (projectName: IProject['project_name']) => `${API.PROJECT_GATEWAYS.BASE(projectName)}/delete`,
        DETAILS: (projectName: IProject['project_name']) => `${API.PROJECT_GATEWAYS.BASE(projectName)}/get`,
        SET_DEFAULT: (projectName: IProject['project_name']) => `${API.PROJECT_GATEWAYS.BASE(projectName)}/set_default`,
        SET_WILDCARD_DOMAIN: (projectName: IProject['project_name']) =>
            `${API.PROJECT_GATEWAYS.BASE(projectName)}/set_wildcard_domain`,

        // TEST_DOMAIN: (projectName: IProject['project_name'], instanceName: string) =>
        //     `${API.PROJECT_GATEWAYS.DETAILS(projectName, instanceName)}/test_domain`,
    },

    RUNS: {
        BASE: () => `${API.BASE()}/runs`,
        LIST: () => `${API.RUNS.BASE()}/list`,
    },

    FLEETS: {
        BASE: () => `${API.BASE()}/fleets`,
        LIST: () => `${API.FLEETS.BASE()}/list`,
    },

    INSTANCES: {
        BASE: () => `${API.BASE()}/instances`,
        LIST: () => `${API.INSTANCES.BASE()}/list`,
    },

    SERVER: {
        BASE: () => `${API.BASE()}/server`,
        INFO: () => `${API.SERVER.BASE()}/get_info`,
    },

    VOLUME: {
        BASE: () => `${API.BASE()}/volumes`,
        LIST: () => `${API.VOLUME.BASE()}/list`,
    },
};
