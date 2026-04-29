# Use Python 3.10 base image
FROM python:3.10

# Set working directory
WORKDIR /code

# Create a non-root user
RUN useradd -m -u 1000 appuser

# Install system-level build dependencies required for fasttext and other packages
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libpq-dev \
    git \
    curl \
    tesseract-ocr \
    tesseract-ocr-all \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY ./pyproject.toml /code/pyproject.toml
COPY ./README.md /code/README.md
COPY ./src /code/src

# Disable Tesseract's internal OpenMP parallelism so workers don't oversubscribe CPUs
ENV OMP_THREAD_LIMIT=1

# Upgrade pip, setuptools, and wheel, and install Python dependencies
RUN pip install --upgrade pip setuptools hatchling
RUN pip install .
# Expose application port
EXPOSE 8080

# Copy and configure entrypoint script
# COPY entrypoint.sh /code/entrypoint.sh
# RUN chmod +x /code/entrypoint.sh && chown -R appuser:appuser /code

# Give appuser ownership of /code so it can write logs
RUN chown -R appuser:appuser /code

# Switch to non-root user
USER appuser
WORKDIR /code
# Define container startup command
#CMD ["sh", "/code/entrypoint.sh"]
CMD ["uvicorn", "translation_service.api:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]