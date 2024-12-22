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
