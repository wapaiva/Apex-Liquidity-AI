import os

# Load environment variables
API_KEY = os.getenv('API_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')

if not API_KEY or not SECRET_KEY:
    raise Exception("API keys are not set. Please set 'API_KEY' and 'SECRET_KEY' in your environment variables.")