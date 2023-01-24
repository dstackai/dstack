const BASE_URL = process.env.API_URL;

export const API = {
    BASE: () => `${BASE_URL}`,
    AUTH: {
        BASE: () => `${API.BASE()}/auth`,
        TOKEN: () => `${API.AUTH.BASE()}/token`,
    },
};
