# AI-API (Python Version)
Simple yet functional RESTful API template that is AI-friendly with Web Scraper functionality. 

Designed to allow AI to receive requests via prompt, and grab any information from any location within a few seconds, and update their knowledge cutoff in relative real time.

---

Functions and an installation guide.

---


Function Descriptions

TaskResource

GET: Retrieves all tasks or a specific task by ID.
POST: Creates a new task.
PUT: Updates an existing task.
DELETE: Deletes a task.


WebScraperResource

POST: Initiates web scraping for a given URL.
scrape_website: Performs the actual web scraping, saving text and images.
same_domain: Checks if two URLs belong to the same domain.
save_text: Saves scraped text to a file.
save_image: Downloads and saves scraped images.


FileResource
GET: Retrieves a saved file (text or image) by filename.


Security Functions
require_api_key: A decorator that ensures all API endpoints require a valid API key.



Installation Guide

Set up the environment:
Copypython -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`

Install required packages:
Copypip install flask flask-restful flask-sqlalchemy flask-migrate marshmallow requests beautifulsoup4 mysqlclient

Set up MySQL:

Install MySQL if not already installed.
Create a new database for the project.
Update the SQLALCHEMY_DATABASE_URI in the code with your MySQL credentials and database name.


Initialize the database:
Copyflask db init
flask db migrate
flask db upgrade

Set environment variables:
Copyexport FLASK_APP=app.py
export FLASK_ENV=development
On Windows, use set instead of export.
Update the API key:

Replace 'your-secret-api-key' in the code with a strong, unique API key.


Run the application:
Copyflask run


Usage

Authentication:
Include the API key in the header of each request:
CopyX-API-Key: your-secret-api-key

Endpoints:

Tasks: /tasks and /tasks/<task_id>
Web Scraping: /scrape
File Retrieval: /files/<filename>


Example API calls:
pythonCopyimport requests

API_KEY = 'your-secret-api-key'
BASE_URL = 'http://localhost:5000'
HEADERS = {'X-API-Key': API_KEY}

# Create a task
response = requests.post(f'{BASE_URL}/tasks', json={'title': 'New Task'}, headers=HEADERS)

# Start web scraping
response = requests.post(f'{BASE_URL}/scrape', json={'url': 'https://example.com'}, headers=HEADERS)

# Retrieve a file
response = requests.get(f'{BASE_URL}/files/some_file.txt', headers=HEADERS)

---

Database Creation


Create a new MySQL database:

sqlCopyCREATE DATABASE ai_friendly_api CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

Create a user and grant privileges:

sqlCopyCREATE USER 'api_user'@'localhost' IDENTIFIED BY 'strong_password';
GRANT ALL PRIVILEGES ON ai_friendly_api.* TO 'api_user'@'localhost';
FLUSH PRIVILEGES;

Update the SQLALCHEMY_DATABASE_URI in the Flask app configuration with these credentials.

Example Database Dump
Included is an example database dump that you can import via phpMyAdmin


This API now provides a solid foundation for building AI-friendly applications with web scraping capabilities, backed by a MySQL database and protected with basic security measures. Remember to adapt and expand upon this base according to your specific requirements and security needs.
