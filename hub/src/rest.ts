import axios, { AxiosInstance, AxiosResponse } from 'axios';

interface IAccessRequestResponse {
    message?: string;
}

class RestAPI {
    private axiosInstance: AxiosInstance;

    constructor() {
        this.axiosInstance = RestAPI.createInstance('');
    }

    static createInstance(authorizationToken: string): AxiosInstance {
        return axios.create({
            baseURL: process.env.API_URL,

            headers: {
                Authorization: `Bearer ${authorizationToken}`,
            },
        });
    }

    setAuthorizationToken(token: string): void {
        this.axiosInstance = RestAPI.createInstance(token);
    }

    async mailchimpSubscribe(params: { email: string }): Promise<IAccessRequestResponse> {
        const { data } = await this.axiosInstance.post<IAccessRequestResponse>('/users/mailchimp/subscribe', params);

        return data;
    }

    async getCurrentUser(): Promise<AxiosResponse> {
        return await this.axiosInstance.get<IUser>('/users/info');
    }
}

export default new RestAPI();
