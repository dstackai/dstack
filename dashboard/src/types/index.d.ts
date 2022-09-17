

declare type TStatus = 'submitted' | 'running' | 'stopping' | 'aborting' | 'stopped' | 'aborted' | 'failed' | 'done' | 'queued'

declare type TVariables = {[key: string]: any};
declare type IVariable = {key: string, value: string};
declare type TApps = IApp[];

declare interface IApp {
    app_name: string;
    job_id: string;
    url: string
}

declare interface SelectOption {
    value: string;
    title: string;
}

declare type AddedEmptyString<Type> = {
    [Property in keyof Type]: Type[Property] | '';
};

declare namespace NodeJS {
    interface ProcessEnv {
        readonly NODE_ENV: 'development' | 'production' | 'test';
        readonly PUBLIC_URL: string;
        readonly LANDING: 'on' | 'off';
        readonly GITHUB_ENABLED: boolean;
        readonly HOST: boolean;
        readonly API_URL: string;
    }
}

declare module '*.avif' {
    const src: string;
    export default src;
}

declare module '*.bmp' {
    const src: string;
    export default src;
}

declare module '*.gif' {
    const src: string;
    export default src;
}

declare module '*.jpg' {
    const src: string;
    export default src;
}

declare module '*.jpeg' {
    const src: string;
    export default src;
}

declare module '*.png' {
    const src: string;
    export default src;
}

declare module '*.webp' {
    const src: string;
    export default src;
}

declare module '*.svg' {
    import * as React from 'react';

    export const ReactComponent: React.FunctionComponent<React.SVGProps<
        SVGSVGElement
        > & { title?: string }>;

    const src: string;
    export default src;
}

declare module '*.module.css' {
    const classes: { readonly [key: string]: string };
    export default classes;
}

declare module '*.module.scss' {
    const classes: { readonly [key: string]: string };
    export default classes;
}

declare module '*.module.sass' {
    const classes: { readonly [key: string]: string };
    export default classes;
}
