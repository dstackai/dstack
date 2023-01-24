const {join} = require('path');

const apiURLs = '/api'

const publicURLs = '/'

// cross-env NODE_ENV=production AUTH_TYPE=github LANDING=on API_URL=/ PUBLIC_URL=/ webpack build --config webpack.config.js

// LANDING: 'on' | 'off'
const landing = process.env.LANDING || 'on';
// HOST: boolean
const host = process.env.HOST || true;
// AUTH_TYPE: 'github' | 'password'
const gitHubEnabled = process.env.GITHUB_ENABLED ? process.env.GITHUB_ENABLED === 'true' : true;
const environment = process.env.NODE_ENV || 'production';
const isProd = environment === 'production';
const isDev = environment === 'development';
const isStage = environment === 'stage';
const rootDir = join(__dirname, '../');
const srcDir = join(__dirname, '../src');
const webpackDir = join(__dirname, './');
const buildDir = join(__dirname, '../build');
const publicDir = join(__dirname, '../public');
const apiUrl = process.env.API_URL || apiURLs;
const publicUrl = process.env.PUBLIC_URL || publicURLs;

const title = "dstack: Git-based CLI to run ML workflows on cloud";
const description = "dstack is an open-source tool that allows you to define ML workflows as code and run them on cloud. " +
    "dstack takes care of dependencies, infrastructure, and data management.";

module.exports = {
    environment,
    landing,
    gitHubEnabled,
    isProd,
    isDev,
    isStage,
    rootDir,
    webpackDir,
    srcDir,
    buildDir,
    publicDir,
    apiUrl,
    publicUrl,
    title,
    description,
    host,
}
