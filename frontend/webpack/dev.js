const webpack = require('webpack');
const { join } = require('path');
const { srcDir } = require('./env');
const ReactRefreshWebpackPlugin = require('@pmmmwh/react-refresh-webpack-plugin');
const CircularDependencyPlugin = require('circular-dependency-plugin');

const port = 3000;

module.exports = {
    mode: 'development',
    entry: [
        `webpack-dev-server/client?http://localhost:${port}`, // bundle the client for webpack-dev-server and connect to the provided endpoint
        join(srcDir, 'index.tsx'), // the entry point of our App
    ],
    devServer: {
        port,
        open: true,
        hot: true, // enable HMR on the server
        historyApiFallback: true, // fixes error 404-ish errors when using react router :see this SO question: https://stackoverflow.com/questions/43209666/react-router-v4-cannot-get-url
        headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
            'Access-Control-Allow-Headers': 'X-Requested-With, content-type, Authorization',
        },
        proxy: [
            {
                context: ['/api'],
                changeOrigin: true,
                target: 'http://127.0.0.1:8000',
                logLevel: 'debug',
            },
        ],
        client: {
            overlay: {
                runtimeErrors: (error) => {
                    return !error.message.includes('ResizeObserver loop completed with undelivered notifications');
                },
            },
        },
    },
    devtool: 'cheap-module-source-map',
    plugins: [
        new webpack.HotModuleReplacementPlugin(), // enable HMR globally
        new ReactRefreshWebpackPlugin(),

        new CircularDependencyPlugin({
            // exclude detection of files based on a RegExp
            exclude: /a\.js|node_modules/,
            // include specific files based on a RegExp
            include: /src/,
            // add errors to webpack instead of warnings
            failOnError: true,
            // allow import cycles that include an asyncronous import,
            // e.g. via import(/* webpackMode: "weak" */ './file.js')
            allowAsyncCycles: false,
            // set the current working directory for displaying module paths
            cwd: process.cwd(),
        }),
    ],
};
