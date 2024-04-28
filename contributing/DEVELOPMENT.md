# Development setup

## Set up the development environment

### 1. Clone the repo:
    ```
    git clone https://github.com/dstackai/dstack
    cd dstack
    ```
   
### 2. (Recommended) Create a virtual environment:
    ```
    python3 -m venv venv
    source venv/bin/activate
    ```
   
### 3. Install `dstack` in editable mode:
    ```
    pip install -e '.[all]'
    ```
   
### 4. Install dev dependencies:
    ```
    pip install -r requirements_dev.txt
    ```
   
### 5. (Recommended) Install pre-commits:
    ```
    pre-commit install
    ```