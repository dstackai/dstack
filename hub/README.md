## Installation

Use `yarn` or `npm` to install dependencies:

```shell
yarn
```

or

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
cp -r build ../cli/dstack/_internal/hub/statics
```

## Development

For frontend development, run a `webpack` dev server:

```shell
npm run start
```

The `webpack` dev server expects the API to be running on `http://127.0.0.1:3001`. So ensure to run the API on port `3001`:

```shell
dstack start --port 3001
```