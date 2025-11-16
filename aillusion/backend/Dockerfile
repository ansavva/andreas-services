# Use an official Python runtime as a parent image
FROM python:3.12.7-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Define environment variable to tell Flask to run in production
ENV FLASK_ENV=production
ENV AUTH0_DOMAIN=aillusion.us.auth0.com
ENV AUTH0_API_ID=https://aillusion-api
ENV APP_URL=https://d1ho48ma8upnwe.cloudfront.net
ENV S3_BUCKET_NAME=aillusion-prod-files-us-east-1
ENV AWS_ACCESS_KEY_ID=AKIA2H5NYU6PTTLY6HNO
ENV AWS_SECRET_ACCESS_KEY=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
ENV AWS_REGION=us-east-1
ENV REPLICATE_API_TOKEN=r8_89dKMqRKhLvC4bznYerQgHVut2u6XKf4MQGdf

# Run the application
#CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "run:app", "--access-logfile", "-", "--error-logfile", "-", "--log-syslog", "--log-syslog-prefix", "gunicorn", "--log-level", "debug"]