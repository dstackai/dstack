import { RouteObject } from 'react-router-dom';

export interface Route extends Omit<RouteObject, 'children'> {
    name?: string;
    children?: Route[];
}
