const webpack = require('webpack');
const {join} = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const FaviconsWebpackPlugin = require('favicons-webpack-plugin');
const CopyPlugin = require("copy-webpack-plugin");
const { environment, publicUrl, apiUrl, isDev, isProd, srcDir, landing, title, description } = require('./env');
const { getStyleLoaders } = require('./getStyleLoaders');

const env = {
    NODE_ENV: JSON.stringify(environment),
    PUBLIC_URL: JSON.stringify(publicUrl),
    API_URL: JSON.stringify(apiUrl),
    ENABLE_API_MOCKING: JSON.stringify(isDev),
};

const sourceMap = !isProd;
const cssRegex = /\.css$/;
const cssModuleRegex = /\.module\.css$/;
const sassRegex = /\.(scss|sass)$/;
const sassModuleRegex = /\.module\.(scss|sass)$/;

module.exports = {
    resolve: {
        modules: ['node_modules', 'src', 'tests'],
        extensions: ['.js', '.jsx', '.ts', '.tsx'],
    },
    module: {
        strictExportPresence: true,
        rules: [
            {
                oneOf: [
                    {
                        test: [/\.jsx?$/],
                        loader: 'babel-loader',
                        exclude: /node_modules/,
                    },
                    {
                        test: /\.tsx?$/,
                        exclude: /node_modules/,
                        loader: 'babel-loader'
                    },
                    {
                        test: /\.svg$/,
                        use: [
                            {
                                loader: require.resolve('@svgr/webpack'),
                                options: {
                                    prettier: false,
                                    svgo: false,
                                    svgoConfig: {
                                        plugins: [{ removeViewBox: false }],
                                    },
                                    titleProp: true,
                                    ref: true,
                                },
                            },
                            {
                                loader: require.resolve('file-loader'),
                                options: {
                                    name: 'static/media/[name].[hash].[ext]',
                                },
                            },
                        ],
                        issuer: {
                            and: [/\.(ts|tsx|js|jsx|md|mdx)$/],
                        },
                    },
                    {
                        test: cssRegex,
                        exclude: [cssModuleRegex, '/node_modules'],
                        use: getStyleLoaders({
                            importLoaders: 1,
                            sourceMap,
                            modules: false,
                        }),
                    },
                    {
                        test: cssModuleRegex,
                        use: getStyleLoaders({
                            importLoaders: 1,
                            sourceMap,
                            modules: {
                                mode: 'local',
                                localIdentName: isDev ? "[local]--[hash:base64:5]" : "[hash:base64:5]",
                            },
                        }),
                    },

                    {
                        test: sassRegex,
                        exclude: sassModuleRegex,
                        use: getStyleLoaders(
                            {
                                importLoaders: 3,
                                sourceMap,
                                modules: {
                                    mode: 'icss',
                                },
                            },
                            'sass-loader'
                        ),
                        sideEffects: true,
                    },
                    {
                        test: sassModuleRegex,
                        use: getStyleLoaders(
                            {
                                importLoaders: 3,
                                sourceMap,
                                modules: {
                                    mode: 'local',
                                    localIdentName: isDev ? "[local]--[hash:base64:5]" : "[hash:base64:5]",
                                },
                            },
                            'sass-loader'
                        ),
                    },
                    {
                        exclude: [/^$/, /\.(js|mjs|jsx|ts|tsx)$/, /\.html$/, /\.json$/],
                        type: 'asset/resource',
                    }
                ]
            }
        ],
    },
    plugins: [
        new HtmlWebpackPlugin({
            template: './public/index.html',
            inject: true,
            publicPath: publicUrl,
            title,
            description,
            landing,

            meta: {
                "og:title": title,
                "og:type": "article",
                // "og:url": publicUrl,
                "og:image": `${publicUrl}splash_thumbnail.png`,
                "og:description": description,
            },

            customHeadHTML: [
                isProd && `
                <script>
                    (function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
                    (i[r].q=i[r].q||[]).push(arguments)};i[r].l=1*new Date();a=s.createElement(o);
                    m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
                    })(window,document,'script','https://www.google-analytics.com/analytics.js','ga');
                    
                    ga('create', 'UA-4493451-5', 'auto');
                    ga('send', 'pageview');
                </script>
                `
            ].filter(Boolean).join('')
        }),

        new CopyPlugin({
            patterns: [
                {
                    from: 'public',
                    globOptions: {
                        ignore: [
                            "**/*.html",
                        ],
                    },
                },
            ],
        }),

        new FaviconsWebpackPlugin(join(srcDir, 'assets/images/favicon.png')),

        new webpack.DefinePlugin({ 'process.env': env }),
    ],
    performance: {
        hints: false,
    },
};
