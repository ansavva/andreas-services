"""
Lambda handler for running Flask app in AWS Lambda
This module adapts the Flask application to work with AWS Lambda
"""
from mangum import Mangum
from src.app import app

# Mangum adapter for AWS Lambda
handler = Mangum(app, lifespan="off")
