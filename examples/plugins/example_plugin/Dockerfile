# Example of including plugins into the dstack server Docker image
FROM dstackai/dstack:latest

# Installing plugin from Docker context
COPY . plugins/example_plugin
RUN uv tool install "dstack[all]" --with plugins/example_plugin

# Installing some other plugins from pypi/git
# RUN uv tool install "dstack[all]" --with plugin1 --with plugin2
