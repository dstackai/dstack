// production config
const {join} = require('path');
const {buildDir, publicPath, srcDir} = require('./env');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');


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
        new MiniCssExtractPlugin(),
    ],
    optimization: {},
};
