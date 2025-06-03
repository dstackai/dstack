const { defineConfig, globalIgnores } = require('eslint/config');
const { BASE_CONFIG } = require('./eslint.config.cjs');

module.exports = defineConfig([
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
    ]),
    { ...BASE_CONFIG },
]);
