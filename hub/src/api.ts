const BASE_URL = process.env.API_URL;

export const API = {
    BASE: () => `${BASE_URL}`,
    USERS: {
        BASE: () => `${API.BASE()}/users`,
        INFO: () => `${API.USERS.BASE()}/token`,
    },

    HUB: {
        BASE: () => `${API.BASE()}/hub`,
        LIST: () => `${API.HUB.BASE()}/list`,
    },
};
