const {isDev, srcDir} = require("./env");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const {join} = require("path");

function getStyleLoaders (cssOptions, preProcessor, preProcessorOptions) {
    const { sourceMap } = cssOptions;

    let loaders = [
        isDev && 'style-loader',
        !isDev && { loader: MiniCssExtractPlugin.loader },
        {
            loader: 'css-loader',
            options: cssOptions,
        },
        {

            loader: 'postcss-loader',
            options: {
                postcssOptions: {
                    plugins: [
                        require('postcss-mixins')({
                            mixinsFiles: join(srcDir, './assets/css/mixins.css'),
                        }),

                        ["postcss-preset-env", {
                            preserve: false,
                            autoprefixer: { grid: true },
                            browsers: ['last 2 versions', "not ie <= 11", "not ie_mob <= 12"],
                            stage: 2,
                            features: {
                                'nesting-rules': true,
                                'custom-media-queries': {
                                    importFrom: join(srcDir, './assets/css/variables.css')
                                },
                                "custom-properties": {
                                    "disableDeprecationNotice": true
                                }
                            },
                            importFrom: [
                                join(srcDir, './assets/css/variables.css'),
                                join(srcDir, './assets/css/mixins.css'),
                            ]
                        }],
                    ],
                },

                sourceMap,
            },
        },
    ].filter(Boolean);

    if (preProcessor) {
        loaders.push(
            {
                loader: require.resolve('resolve-url-loader'),
                options: {
                    sourceMap,
                    root: srcDir,
                },
            },
            {
                loader: require.resolve(preProcessor),
                options: {
                    sourceMap,
                    ...(preProcessorOptions ?? {}),
                },
            }
        );
    }

    return loaders;
}

module.exports = {
    getStyleLoaders: getStyleLoaders
}
