import rest from 'rest';

export class Auth {
    constructor(private storageKey = 'auth-token', private token: string | null = null) {
        this.token = localStorage.getItem(this.storageKey);

        if (this.token) rest.setAuthorizationToken(this.token);
    }

    getToken() {
        return this.token;
    }

    setToken(token: string) {
        this.token = token;
        rest.setAuthorizationToken(this.token);
        localStorage.setItem(this.storageKey, this.token);
    }

    clearToken() {
        this.token = null;
        localStorage.removeItem(this.storageKey);
        rest.setAuthorizationToken('');
    }
}

export default new Auth();
