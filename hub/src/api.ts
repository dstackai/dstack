const BASE_URL = process.env.API_URL;

export const API = {
    BASE: () => `${BASE_URL}`,
    USERS: {
        BASE: () => `${API.BASE()}/users`,
        LIST: () => `${API.USERS.BASE()}/list`,
        DETAILS: (name: IUser['user_name']) => `${API.USERS.BASE()}/${name}`,
        INFO: () => `${API.USERS.BASE()}/info`,
        REFRESH_TOKEN: (name: IUser['user_name']) => `${API.USERS.DETAILS(name)}/refresh-token`,
    },

    PROJECTS: {
        BASE: () => `${API.BASE()}/projects`,
        LIST: () => `${API.PROJECTS.BASE()}/list`,
        DETAILS: (name: IProject['project_name']) => `${API.PROJECTS.BASE()}/${name}`,
        DETAILS_WITH_CONFIG: (name: IProject['project_name']) => `${API.PROJECTS.DETAILS(name)}/config_info`,
        MEMBERS: (name: IProject['project_name']) => `${API.PROJECTS.DETAILS(name)}/members`,
        BACKEND_VALUES: () => `${API.PROJECTS.BASE()}/backends/values`,
    },
};
