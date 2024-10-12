import os
from flask import Flask, request, jsonify, send_file
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from marshmallow import Schema, fields, validate, ValidationError
from datetime import datetime, timedelta
from functools import wraps
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import hashlib
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://username:password@localhost/ai_friendly_api'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'scraped_files'
app.config['API_KEY'] = os.environ.get('API_KEY', 'your-secret-api-key')  # Use environment variable in production
app.config['RATE_LIMIT'] = "100 per day;10 per hour"
app.config['PAGE_SIZE'] = 20

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
api = Api(app)
limiter = Limiter(app, key_func=get_remote_address)

# Ensure upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Set up logging
logging.basicConfig(filename='api.log', level=logging.INFO)
logger = logging.getLogger(__name__)

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

class APIRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    endpoint = db.Column(db.String(255), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

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
            logger.warning(f"Unauthorized access attempt from IP: {request.remote_addr}")
            return {"error": "Unauthorized", "message": "Invalid or missing API Key"}, 401
    return decorated_function

def log_request():
    api_request = APIRequest(
        ip_address=request.remote_addr,
        endpoint=request.endpoint,
        method=request.method
    )
    db.session.add(api_request)
    db.session.commit()

# Error handling
@app.errorhandler(HTTPException)
def handle_exception(e):
    """Return JSON instead of HTML for HTTP errors."""
    response = e.get_response()
    response.data = json.dumps({
        "code": e.code,
        "name": e.name,
        "description": e.description,
    })
    response.content_type = "application/json"
    return response

# Custom exceptions
class RateLimitExceeded(Exception):
    pass

@app.errorhandler(RateLimitExceeded)
def handle_rate_limit_exceeded(e):
    return {"error": "Rate limit exceeded", "message": str(e)}, 429

# Resources
class TaskListResource(Resource):
    @require_api_key
    @limiter.limit(app.config['RATE_LIMIT'])
    def get(self):
        log_request()
        page = int(request.args.get('page', 1))
        tasks = Task.query.paginate(page=page, per_page=app.config['PAGE_SIZE'])
        return jsonify({
            "tasks": [task_schema.dump(task) for task in tasks.items],
            "page": tasks.page,
            "total_pages": tasks.pages,
            "total_items": tasks.total
        })

    @require_api_key
    @limiter.limit(app.config['RATE_LIMIT'])
    def post(self):
        log_request()
        json_data = request.get_json()
        if not json_data:
            return {"error": "Bad Request", "message": "No input data provided"}, 400
        try:
            data = task_schema.load(json_data)
        except ValidationError as err:
            return {"error": "Validation Error", "message": err.messages}, 422
        task = Task(**data)
        db.session.add(task)
        db.session.commit()
        return jsonify(task_schema.dump(task)), 201

class TaskResource(Resource):
    @require_api_key
    @limiter.limit(app.config['RATE_LIMIT'])
    def get(self, task_id):
        log_request()
        task = Task.query.get_or_404(task_id)
        return jsonify(task_schema.dump(task))

    @require_api_key
    @limiter.limit(app.config['RATE_LIMIT'])
    def put(self, task_id):
        log_request()
        task = Task.query.get_or_404(task_id)
        json_data = request.get_json()
        if not json_data:
            return {"error": "Bad Request", "message": "No input data provided"}, 400
        try:
            data = task_schema.load(json_data, partial=True)
        except ValidationError as err:
            return {"error": "Validation Error", "message": err.messages}, 422
        for key, value in data.items():
            setattr(task, key, value)
        db.session.commit()
        return jsonify(task_schema.dump(task))

    @require_api_key
    @limiter.limit(app.config['RATE_LIMIT'])
    def delete(self, task_id):
        log_request()
        task = Task.query.get_or_404(task_id)
        db.session.delete(task)
        db.session.commit()
        return "", 204

class WebScraperResource(Resource):
    @require_api_key
    @limiter.limit(app.config['RATE_LIMIT'])
    def post(self):
        log_request()
        json_data = request.get_json()
        if not json_data or 'url' not in json_data:
            return {"error": "Bad Request", "message": "No URL provided"}, 400
        
        url = json_data['url']
        max_pages = json_data.get('max_pages', 10)  # Default to 10 pages
        
        try:
            scraped_data = self.scrape_website(url, max_pages)
            return jsonify(scraped_data), 200
        except Exception as e:
            logger.error(f"Error occurred while scraping: {str(e)}")
            return {"error": "Internal Server Error", "message": f"Error occurred while scraping: {str(e)}"}, 500

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
                logger.error(f"Error scraping {url}: {str(e)}")

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
            logger.error(f"Error saving image {img_url}: {str(e)}")
        return None

class FileResource(Resource):
    @require_api_key
    @limiter.limit(app.config['RATE_LIMIT'])
    def get(self, filename):
        log_request()
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            return send_file(filepath)
        return {"error": "Not Found", "message": "File not found"}, 404

# Routes
api.add_resource(TaskListResource, '/api/v1/tasks')
api.add_resource(TaskResource, '/api/v1/tasks/<int:task_id>')
api.add_resource(WebScraperResource, '/api/v1/scrape')
api.add_resource(FileResource, '/api/v1/files/<path:filename>')

if __name__ == '__main__':
    app.run(debug=False)  # Set to False in production
