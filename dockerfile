# Base image with Python 3.11
#FROM python:3

# Set the working directory in the container
WORKDIR /app

# Copy all files from the current directory (host) to the working directory (/app) in the container
COPY . /app

# Ensure Python's package path is recognized
ENV PYTHONPATH="/app:/usr/local/lib/python3.11/site-packages"

# Install pip dependencies
RUN python -m ensurepip --upgrade && \
    python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

# Expose the port your Flask health check will run on
EXPOSE 8080

# Start the application
CMD ["python3", "main.py"]