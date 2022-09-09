import { generatePath, RouteObject } from 'react-router-dom';
import { Route } from './types';
import { RouterModules, setRouterModule } from './exports';
import { index as routes } from './routes';
import { hostRoutes } from './host-routes';

type RouterUrlParams = {
    [key: string]: any;
};

class ApplicationRouter {
    private routes: Route[];

    constructor(routes: Route[]) {
        this.routes = routes;
    }

    private routeToReactRouterRouteObject(route: Route): RouteObject {
        const { name, children, ...props } = route;
        const newChildren = children?.length ? children.map((r) => this.routeToReactRouterRouteObject(r)) : undefined;

        return {
            ...props,
            children: newChildren,
        };
    }

    public getReactRouterRoutes(): RouteObject[] {
        return this.routes.map((r) => this.routeToReactRouterRouteObject(r));
    }

    private getPathByPathName(namePath: string[], routes: Route[]): string {
        const name = namePath.shift();
        const route = routes.find((r) => r.name === name);

        if (!route) return '';

        if (namePath.length && route.children?.length) {
            const nestedPath = this.getPathByPathName(namePath, route.children);
            if (nestedPath) return [route.path, nestedPath].filter(Boolean).join('/').replace(/^\/\//, '/');
        }

        return route.path ?? '';
    }

    public buildUrl(pathName: string, params?: RouterUrlParams): string {
        const routeNames = pathName.split('.');

        const url = this.getPathByPathName(routeNames, this.routes);

        if (params) return generatePath(url, params);

        return url;
    }
}

export const newRouter = new ApplicationRouter(process.env.HOST ? hostRoutes : routes);

setRouterModule(RouterModules.NEW_ROUTER, newRouter);
