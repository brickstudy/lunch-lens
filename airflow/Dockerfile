FROM apache/airflow:2.10.3-python3.11

USER root

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Copy requirements file
COPY ./requirements.txt /opt/airflow/requirements.txt

# Install Python packages
RUN pip install --no-cache-dir -r /opt/airflow/requirements.txt
