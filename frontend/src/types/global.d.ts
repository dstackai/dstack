declare var Tally: {
    openPopup: (string) => void;
    closePopup: (string) => void;
};

declare type AddedEmptyString<Type> = {
    [Property in keyof Type]: Type[Property] | '';
};

declare type DateTime = string;

declare type TBaseRequestListParams = {
    prev_created_at?: string;
    prev_id?: string;
    limit?: number;
    ascending?: boolean;
};

declare interface HashMap<T = any> {
    [key: string]: T;
}

declare namespace NodeJS {
    interface ProcessEnv {
        readonly NODE_ENV: 'development' | 'production' | 'test';
        readonly UI_VERSION: 'sky' | 'enterprise';
        readonly PUBLIC_URL: string;
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

    export const ReactComponent: React.FunctionComponent<React.SVGProps<SVGSVGElement> & { title?: string }>;

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
