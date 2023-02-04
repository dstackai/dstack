const BASE_URL = process.env.API_URL;

export const API = {
    BASE: () => `${BASE_URL}`,
    USERS: {
        BASE: () => `${API.BASE()}/users`,
        LIST: () => `${API.USERS.BASE()}/list`,
        DETAILS: (name: IUser['user_name'] | string) => `${API.USERS.BASE()}/${name}`,
        INFO: () => `${API.USERS.BASE()}/info`,
    },

    HUBS: {
        BASE: () => `${API.BASE()}/hubs`,
        LIST: () => `${API.HUBS.BASE()}/list`,
    },
};
