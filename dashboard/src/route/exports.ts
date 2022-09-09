export enum RouterModules {
    NEW_ROUTER = 'NEW_ROUTER',
}

export const routerModules: { [key: string]: any } = {};

export const setRouterModule = (key: string, val: any): void => {
    routerModules[key] = val;
};

export const getRouterModule = (key: string): any => {
    return routerModules[key];
};
