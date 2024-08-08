// production config
const {join} = require('path');
const {buildDir, publicPath, srcDir} = require('./env');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const CssMinimizerPlugin = require('css-minimizer-webpack-plugin');


module.exports = {
    mode: "production",
    entry: join(srcDir, 'index.tsx'),
    output: {
        path: buildDir,
        filename: "[name]-[contenthash].js",
        publicPath: publicPath,
        clean: true,
    },
    devtool: "source-map",
    plugins: [
        new MiniCssExtractPlugin({
            filename: "[name]-[contenthash].css",
        }),
    ],
    optimization: {
        minimize: true,
        minimizer: [new CssMinimizerPlugin()]
    },
};
