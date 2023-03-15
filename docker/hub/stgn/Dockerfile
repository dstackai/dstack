FROM python:3.9-slim

ARG VERSION
ENV VERSION=$VERSION
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade setuptools wheel
RUN pip3 install --upgrade fastapi
RUN pip3 install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple dstack==$VERSION

EXPOSE 3000

ENTRYPOINT ["dstack", "hub", "start", "--server.address=0.0.0.0"]