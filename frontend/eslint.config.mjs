import { defineConfig, globalIgnores } from 'eslint/config';
import i18N from 'eslint-plugin-i18n';
import simpleImportSort from 'eslint-plugin-simple-import-sort';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FlatCompat } from '@eslint/eslintrc';
import js from '@eslint/js';
import typescriptEslint from '@typescript-eslint/eslint-plugin';
import tsParser from '@typescript-eslint/parser';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const compat = new FlatCompat({
    baseDirectory: __dirname,
    recommendedConfig: js.configs.recommended,
    allConfig: js.configs.all,
});

export const BASE_CONFIG = {
    extends: compat.extends(
        'eslint:recommended',
        'plugin:@typescript-eslint/eslint-recommended',
        'plugin:@typescript-eslint/recommended',
        'prettier',
        'plugin:prettier/recommended',
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

export default defineConfig([
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
