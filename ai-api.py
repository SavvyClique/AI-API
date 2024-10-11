# Neverslain Labs - unsub42@gmail.com

import os
from flask import Flask, request, jsonify, send_file
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from marshmallow import Schema, fields, validate, ValidationError
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import hashlib
from functools import wraps

app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://username:password@localhost/dbname'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'scraped_files'
app.config['API_KEY'] = 'your-secret-api-key'  # Store this securely in production

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
api = Api(app)

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Models
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ScrapedData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    text_file = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ScrapedImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    scraped_data_id = db.Column(db.Integer, db.ForeignKey('scraped_data.id'), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    filename = db.Column(db.String(255), nullable=False)

# Schemas
class TaskSchema(Schema):
    id = fields.Int(dump_only=True)
    title = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    description = fields.Str(validate=validate.Length(max=500))
    status = fields.Str(validate=validate.OneOf(['pending', 'in_progress', 'completed']))
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

task_schema = TaskSchema()

# Security
def require_api_key(view_function):
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        if request.headers.get('X-API-Key') and request.headers.get('X-API-Key') == app.config['API_KEY']:
            return view_function(*args, **kwargs)
        else:
            return {"message": "Invalid or missing API Key"}, 401
    return decorated_function

# Resources
class TaskResource(Resource):
    @require_api_key
    def get(self, task_id=None):
        if task_id is None:
            tasks = Task.query.all()
            return jsonify([task_schema.dump(task) for task in tasks])
        task = Task.query.get_or_404(task_id)
        return jsonify(task_schema.dump(task))

    @require_api_key
    def post(self):
        json_data = request.get_json()
        if not json_data:
            return {"message": "No input data provided"}, 400
        try:
            data = task_schema.load(json_data)
        except ValidationError as err:
            return err.messages, 422
        task = Task(**data)
        db.session.add(task)
        db.session.commit()
        return jsonify(task_schema.dump(task)), 201

    @require_api_key
    def put(self, task_id):
        task = Task.query.get_or_404(task_id)
        json_data = request.get_json()
        if not json_data:
            return {"message": "No input data provided"}, 400
        try:
            data = task_schema.load(json_data, partial=True)
        except ValidationError as err:
            return err.messages, 422
        for key, value in data.items():
            setattr(task, key, value)
        db.session.commit()
        return jsonify(task_schema.dump(task))

    @require_api_key
    def delete(self, task_id):
        task = Task.query.get_or_404(task_id)
        db.session.delete(task)
        db.session.commit()
        return "", 204

class WebScraperResource(Resource):
    @require_api_key
    def post(self):
        json_data = request.get_json()
        if not json_data or 'url' not in json_data:
            return {"message": "No URL provided"}, 400
        
        url = json_data['url']
        max_pages = json_data.get('max_pages', 10)  # Default to 10 pages
        
        try:
            scraped_data = self.scrape_website(url, max_pages)
            return jsonify(scraped_data), 200
        except Exception as e:
            return {"message": f"Error occurred while scraping: {str(e)}"}, 500

    def scrape_website(self, start_url, max_pages):
        visited = set()
        to_visit = [start_url]
        scraped_data = []

        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue

            try:
                response = requests.get(url)
                soup = BeautifulSoup(response.content, 'html.parser')

                # Extract text
                text = soup.get_text()
                text_filename = self.save_text(url, text)

                # Save scraped data to database
                scraped_page = ScrapedData(url=url, text_file=text_filename)
                db.session.add(scraped_page)
                db.session.commit()

                # Extract images
                images = []
                for img in soup.find_all('img', src=True):
                    img_url = urljoin(url, img['src'])
                    img_filename = self.save_image(img_url)
                    if img_filename:
                        scraped_image = ScrapedImage(scraped_data_id=scraped_page.id, url=img_url, filename=img_filename)
                        db.session.add(scraped_image)
                        images.append({"url": img_url, "filename": img_filename})

                db.session.commit()

                scraped_data.append({
                    "url": url,
                    "text_file": text_filename,
                    "images": images
                })

                visited.add(url)

                # Find links to other pages on the same domain
                for link in soup.find_all('a', href=True):
                    href = urljoin(url, link['href'])
                    if self.same_domain(url, href) and href not in visited:
                        to_visit.append(href)

            except Exception as e:
                print(f"Error scraping {url}: {str(e)}")

        return {
            "scraped_pages": len(scraped_data),
            "data": scraped_data
        }

    def same_domain(self, url1, url2):
        return urlparse(url1).netloc == urlparse(url2).netloc

    def save_text(self, url, text):
        filename = hashlib.md5(url.encode()).hexdigest() + ".txt"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(text)
        return filename

    def save_image(self, img_url):
        try:
            response = requests.get(img_url)
            if response.status_code == 200:
                filename = hashlib.md5(img_url.encode()).hexdigest() + "." + img_url.split('.')[-1]
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                return filename
        except Exception as e:
            print(f"Error saving image {img_url}: {str(e)}")
        return None

class FileResource(Resource):
    @require_api_key
    def get(self, filename):
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            return send_file(filepath)
        return {"message": "File not found"}, 404

# Routes
api.add_resource(TaskResource, '/tasks', '/tasks/<int:task_id>')
api.add_resource(WebScraperResource, '/scrape')
api.add_resource(FileResource, '/files/<path:filename>')

if __name__ == '__main__':
    app.run(debug=True)
