# Frontend development setup

To work with the frontend, switch the current folder to [frontend](../frontend)

```shell
cd frontend
```

## Building the frontend

### 1. Install NPM dependencies

Use `npm` to install dependencies:

```shell
npm install
```

### 2. Build the frontend

For building the frontend, run:

```shell
npm run build
```

### 3. Copy the compiled frontend files

Copy the contents of the `frontend/build` directory to the backend directory (`src/dstack/_internal/server/statics`):

```shell
cp -r build/ ../src/dstack/_internal/server/statics/
```

### 4. Run the dstack server

Now, if you've installed `dstack` in editable mode, you can simply run `dstack server`
and the frontend will be working.

```shell
dstack server
```

## Developing the frontend

For frontend development, run a `webpack` dev server:

```shell
npm run start
```

The `webpack` dev server expects the API to be running on `http://127.0.0.1:8000`. So ensure to run the API on port `8000`:

```shell
dstack server --port 8000
```

## Product flavors

The shared frontend supports OSS, Enterprise, Factory, and Sky. From `frontend/`, use
`npm run build`, `npm run build-enterprise`, `npm run build-factory`, or
`npm run build-sky`; the corresponding development commands are `start`,
`start-enterprise`, `start-factory`, and `start-sky`.

`frontend/product.config.cjs` defines product names and inherited UI features for both
webpack and the application. Components use `product` from `src/product.ts` instead of
checking `UI_VERSION` directly. Factory and Sky share billing and presets; hosted-service
content such as Sky terms and onboarding uses `product.isSky`.

All flavors use the same login component. It displays supported providers enabled by
`/api/auth/list_providers`, independently of the UI flavor, and always offers token login.
