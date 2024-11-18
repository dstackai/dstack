import { isValidUrl } from 'libs';

export const getModelGateway = (baseUrl?: IModel['base_url']) => {
    if (!baseUrl) {
        return '';
    }

    if (isValidUrl(baseUrl)) {
        return baseUrl;
    }

    return document.location.origin + baseUrl;
};
