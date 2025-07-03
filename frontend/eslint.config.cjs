const { defineConfig, globalIgnores } = require('eslint/config');
const i18N = require('eslint-plugin-i18n');
const simpleImportSort = require('eslint-plugin-simple-import-sort');
const { FlatCompat } = require('@eslint/eslintrc');
const js = require('@eslint/js');
const typescriptEslint = require('@typescript-eslint/eslint-plugin');
const tsParser = require('@typescript-eslint/parser');

const compat = new FlatCompat({
    baseDirectory: __dirname,
    recommendedConfig: js.configs.recommended,
    allConfig: js.configs.all,
});

const BASE_CONFIG = {
    extends: compat.extends(
        'eslint:recommended',
        'plugin:@typescript-eslint/eslint-recommended',
        'plugin:@typescript-eslint/recommended',
        'prettier',
        'plugin:prettier/recommended'
    ),

    plugins: {
        '@typescript-eslint': typescriptEslint,
        i18n: i18N,
        'simple-import-sort': simpleImportSort,
    },

    languageOptions: {
        parser: tsParser,
    },

    rules: {
        'i18n/no-russian-character': 1,

        'simple-import-sort/imports': [
            'error',
            {
                groups: [
                    ['^react', 'lodash', '^\\w', '^@?\\w'],
                    ['^components', '^layouts'],
                    ['^consts', '^hooks', '^libs', '^routes', '^services', '^types'],
                    ['^App', '^pages'],
                    ['^\\./(?=.*/)(?!/?$)', '^\\.(?!/?$)', '^\\./?$'],
                    ['./constants/.'],
                    ['./definitions/.', './types'],
                    ['^.+\\.svg', '^.+\\.png$', '^.+\\.jpg', '^.+\\.s?css$'],
                ],
            },
        ],
    },
};

module.exports = defineConfig([
    globalIgnores([
        'node_modules',
        'build',
        'server.js',
        'src/locale',
        'src/types',
        'src/setupProxy.js',
        'webpack/**/*',
        'webpack/env.js',
        'webpack/prod.js',
        'public',
        'staticServer.js',
        'webpack.config.js',
    ]),
    { ...BASE_CONFIG },
]);
