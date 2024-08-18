const { merge } = require("webpack-merge");
const base = require("./webpack/base");
const dev = require("./webpack/dev");
const prod = require("./webpack/prod");

const {isDev} = require('./webpack/env');

module.exports = isDev ? merge(base, dev) : merge(base, prod);
