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

    HUBS: {
        BASE: () => `${API.BASE()}/hubs`,
        LIST: () => `${API.HUBS.BASE()}/list`,
        DETAILS: (name: IHub['hub_name']) => `${API.HUBS.BASE()}/${name}`,
        MEMBERS: (name: IHub['hub_name']) => `${API.HUBS.DETAILS(name)}/members`,
        BACKEND_VALUES: () => `${API.HUBS.BASE()}/backends/values`,
    },
};
