# ASTRA-Interface AWS Deployment Guide

To ensure zero errors when deploying the ASTRA Mission Control Platform to AWS, the codebase has been structured to cloud-native WSGI standards. Everything is pre-configured.

## Included Cloud Configurations
1. **`Procfile`**: Directs AWS/Heroku/Render to use `gunicorn` (a production WSGI HTTP Server) as the startup command.
2. **`whitenoise`**: Integrated into `app.py`. In production, Flask should never serve static files. WhiteNoise wraps the Flask app and serves `static/` files directly and efficiently.
3. **`.ebextensions/01_flask.config`**: Explicit configurations for AWS Elastic Beanstalk (AWS EB) so it properly targets `app:app` instead of looking for `application.py`.
4. **`.gitignore`**: Guarantees you will never accidentally push your `astra_platform.db` (containing AES-encrypted passwords) or local `.env` variables to GitHub.

## Deployment Steps (AWS Elastic Beanstalk)

Deploying via AWS Elastic Beanstalk is the easiest standard path for Python applications.

1. **Install the Awsebcli (Optional but recommended):**
   ```bash
   pip install awsebcli
   ```

2. **Initialize your AWS EB Environment:**
   Run this in your interface folder:
   ```bash
   eb init -p python-3.11 astra-mission-control --region us-east-1
   ```
   *(Select Yes if it asks to set up SSH).*

3. **Set your Secret Key on AWS (CRITICAL!):**
   The Fernet encryption relies on `ASTRA_SECRET_KEY`. Set this in the AWS console, or via the CLI *before* creating the environment:
   ```bash
   eb setenv ASTRA_SECRET_KEY="replace-this-with-a-very-long-secure-random-string"
   ```
   > ⚠️ **Warning:** Once you set `ASTRA_SECRET_KEY` and save credentials, **DO NOT CHANGE IT**. If you change the secret key later, all existing Space-Track credentials in the database will become un-decryptable, and users (including you) will have to re-enter them in the UI.

4. **Create the Environment and Deploy:**
   ```bash
   eb create astra-production-env
   ```
   AWS will zip the code, read `requirements.txt` (which now correctly installs `gunicorn`, `whitenoise`, and `astra-core-engine`), run the `Procfile`, and start the app on port 80.

5. **Subsequent Updates:**
   After making changes locally, just commit your code and run:
   ```bash
   eb deploy
   ```

## Note on the Database
This application uses SQLite (`astra_platform.db`). On AWS Elastic Beanstalk, instances can be ephemeral (they restart or scale). If an instance is rebuilt, the local SQLite database resets. 
For a true production environment with long-term persistence, you should provision a small **Amazon RDS PostgreSQL** instance and change the connection string in `database.py`. However, for a single-instance MVP deployment, this SQLite setup will work perfectly!
