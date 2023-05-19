const {join} = require('path');

const apiURLs = '/api'

const publicURLs = '/'

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

const title = "dstack";
const description = "dstack offers a unified and simple interface for ML engineers to manage dev environments and run " +
    "                    pipelines and apps cost-effectively on AWS, GCP, and Azure.";

module.exports = {
    environment,
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
}
