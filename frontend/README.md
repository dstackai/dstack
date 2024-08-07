## Installation

Use `npm` to install dependencies:

```shell
npm install
```

## Build

For building the frontend, run:

```shell
npm run build
```

Then copy the build directory:

```shell
cp -r build ../src/dstack_cloud/statics
```

## Development

For frontend development, run a `webpack` dev server:

```shell
npm run start
```

The `webpack` dev server expects the API to be running on `http://127.0.0.1:3001`. So ensure to run the API on port `3001`:

```shell
dstack server --port 3001
```