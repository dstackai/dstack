import { defineConfig, globalIgnores } from 'eslint/config';

import { BASE_CONFIG } from './eslint.config.mjs';

export default defineConfig([
    globalIgnores([
        'frontend/node_modules',
        'frontend/build',
        'frontend/server.js',
        'frontend/src/locale',
        'frontend/src/types',
        'frontend/src/setupProxy.js',
        'frontend/webpack/**/*',
        'frontend/webpack/env.js',
        'frontend/webpack/prod.js',
        'frontend/public',
        'frontend/staticServer.js',
        'frontend/webpack.config.js',
        'docs/**/*',
    ]),

    { ...BASE_CONFIG },
]);
