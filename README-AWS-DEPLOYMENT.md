# ASTRA-Interface AWS Deployment Guide

To ensure zero errors when deploying the ASTRA Mission Control Platform to AWS, the codebase has been structured to cloud-native WSGI standards and adapted for horizontal scaling using Amazon Elastic Beanstalk (EC2), Amazon S3, and Amazon RDS.

## Included Cloud Configurations
1. **`Procfile`**: Directs AWS to use `gunicorn` (a production WSGI HTTP Server) as the startup command.
2. **`database.py` (SQLAlchemy)**: Automatically maps your database logic. It uses SQLite locally for easy testing, but seamlessly switches to PostgreSQL/MySQL if deployed using RDS with a `DATABASE_URL`.
3. **`storage.py` (Boto3)**: Allows the application to offload heavy static assets directly to an S3 bucket or CloudFront distribution, alleviating pressure from the EC2 web nodes.
4. **`/api/health` Endpoint**: Configured dynamically to test the database pipeline so that AWS Application Load Balancers can auto-scale and verify instances.
5. **`.ebextensions/01_flask.config`**: Explicit configurations for AWS Elastic Beanstalk to correctly target the `app:app` application instead of `application.py`.

---

## Deployment Steps (AWS Elastic Beanstalk)

Deploying via AWS Elastic Beanstalk (EB) is the standard and easiest path for Python applications on AWS, automatically managing EC2, Load Balancing, and Auto-Scaling.

### Step 1: Install AWS EB CLI
If you haven't already:
```bash
pip install awsebcli
```

### Step 2: Initialize your AWS EB Environment
Run this in your interface folder:
```bash
eb init -p python-3.11 astra-mission-control --region us-east-1
```
*(Select Yes if it asks to set up SSH).*

### Step 3: Provision AWS RDS & S3 (Production Infrastructure)
Before spinning up the EC2 instances, you should create the persistent layers:
1. **Amazon RDS**: Create a PostgreSQL database. Retrieve the connection string (e.g., `postgresql://user:password@endpoint:5432/db_name`).
2. **Amazon S3**: Create an S3 bucket for your static assets. Ensure the bucket policy allows public reading of static files (or deploy via CloudFront).

### Step 4: Set Environment Variables on AWS (CRITICAL)
Your EB Environment needs to know your keys and endpoints before it launches to properly initialize SQLAlchemy and Boto3.

```bash
eb setenv ASTRA_SECRET_KEY="replace-this-with-a-very-long-secure-random-string" \
DATABASE_URL="postgresql://username:password@your-rds-endpoint.amazonaws.com:5432/astradb" \
AWS_S3_BUCKET="your-production-bucket-name"
```

> ⚠️ **Warning on Encryption:** The Fernet encryption relies on `ASTRA_SECRET_KEY`. Once you set it and save credentials, **DO NOT CHANGE IT**. Changing this key irreversibly encrypts existing Space-Track credentials in the database.

### Step 5: Create the Environment and Deploy
AWS relies on `ALB` (Application Load Balancer) to manage multiple EC2 instances. Launch your environment:
```bash
eb create astra-production-env
```

Wait 5-10 minutes. AWS will:
1. Provision EC2 instance(s).
2. Install all `requirements.txt` dependencies (SQLAlchemy, `boto3`, `gunicorn`, etc.).
3. Ping `/api/health` to ensure the instances can reach RDS successfully. If it connects, traffic routing begins immediately.

### Step 6: Subsequent Updates
After making changes locally, just commit your code and run:
```bash
eb deploy
```

---

## Local Development (Fallback Mode)
If you do not specify `DATABASE_URL` and `AWS_S3_BUCKET` on your local machine, the application elegantly falls back out of AWS mode. `SQLAlchemy` will build a local `astra_platform.db` SQLite file, and `WhiteNoise` will serve local static files, allowing you to develop without incurring AWS costs.
