# Development setup

## 1. Clone the repo:

```shell
git clone https://github.com/dstackai/dstack
cd dstack
```
   
## 2. (Recommended) Create a virtual environment:

```shell
python3 -m venv venv
source venv/bin/activate
```
   
## 3. Install `dstack` in editable mode:

```shell
pip install -e '.[all]'
```
   
## 4. Install dev dependencies:

```shell
pip install -r requirements_dev.txt
```
   
## 5. (Recommended) Install pre-commits:

```shell
pre-commit install
```

## 6. Frontend

See [FRONTEND.md](FRONTEND.md) for the details on how to build and develop the frontend.