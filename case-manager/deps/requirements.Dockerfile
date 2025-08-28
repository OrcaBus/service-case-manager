# this will create the asset of requirements-slim dependencies with docker
# the output is located at `/output/python` within the container

FROM public.ecr.aws/lambda/python:3.13

WORKDIR /home

# Copy requirements.txt
COPY case-manager/deps/requirements.txt .

# making python folder where as guided in the AWS lambda layer docs
RUN mkdir -p output/python

# Install the specified packages
RUN pip install -r requirements.txt -t output/python
