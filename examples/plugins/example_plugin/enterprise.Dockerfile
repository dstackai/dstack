# Example of including plugins into the dstack Enterprise Docker image
FROM ghcr.io/dstackai/dstack-enterprise:latest

# Installing plugin from Docker context
COPY . plugins/example_plugin
RUN uv pip install plugins/example_plugin

# Installing some other plugins from pypi/git
# RUN uv pip install plugin-name
