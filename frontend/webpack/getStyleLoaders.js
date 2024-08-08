const {isDev, srcDir} = require("./env");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

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
                        ["postcss-preset-env", {
                            autoprefixer: { flexbox: 'no-2009', },
                            browsers: ['last 2 versions', "not ie <= 11", "not ie_mob <= 12"],
                            stage: 3,
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
