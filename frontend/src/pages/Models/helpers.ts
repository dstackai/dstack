import { isValidUrl } from 'libs';

export const getModelGateway = (baseUrl: IModel['base_url']) => {
    if (isValidUrl(baseUrl)) {
        return baseUrl;
    }

    return document.location.origin + baseUrl;
};
