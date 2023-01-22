/* eslint-disable no-console */
const express = require('express');
const path = require('path');
const { createProxyMiddleware } = require('http-proxy-middleware');

const app = express();

const proxy = {
    '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
    },
};

const port = parseInt(process.env.PORT, 10) || 3001;

if (proxy) {
    Object.keys(proxy).forEach(function (context) {
        app.use(createProxyMiddleware(context, proxy[context]));
    });
}

app.use(express.static('build'));

app.get('*', (req, res) => {
    res.sendFile(path.resolve(__dirname, 'build', 'index.html'));
});

app.listen(port, () => console.log(`server has been started on ${port}`));
