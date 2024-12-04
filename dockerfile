# Base image with Python 3.11
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /

# Copy all files from the current directory (host) to the working directory (/app) in the container
COPY . /
# Ensure Python's package path is recognized
#ENV PYTHONPATH="/app:/usr/local/lib/python3.11/site-packages"

# Install pip dependencies
RUN python3 -m ensurepip --upgrade && \
    python3 -m pip install --upgrade pip && \
    python3 -m pip install -r requirements.txt

# Expose the port your Flask health check will run on
EXPOSE 8080

# Start the application
CMD ["python3", "main.py"]