import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask import send_file
from flask import send_from_directory
from werkzeug.utils import secure_filename
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = True
app.config['UPLOAD_FOLDER_DOWNLOADS'] = '/static/downloads'
app.config['UPLOAD_FOLDER_PICTS'] = '/static/picts'
app.secret_key = 'secret_salt'  # Change this on Public build!
db = SQLAlchemy(app)

app_name = 'ClubSite'


def check_permissions(required_permissions):
    if 'username' not in session:
        return False
    session_user = db.session.get(User, session['user_id'])
    for permission in required_permissions:
        if not getattr(session_user, permission):
            return False
    return True


def requires_permission(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not check_permissions([permission]):
                return redirect(url_for('login'))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    leader = db.Column(db.Boolean, default=False)
    author = db.Column(db.Boolean, default=False)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    project_link = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship("User", backref="projects")
    download_id = db.Column(db.Integer, db.ForeignKey('downloads.id'), nullable=True)
    download = db.relationship("Downloads", backref="projects")


class Downloads(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(100), nullable=False)
    file = db.Column(db.String(100), nullable=False)


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    image_path = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship("User", backref="news")


def create_default_user():
    admin_user = User(username='admin', password=generate_password_hash('password'), leader=True, author=True)
    db.session.add(admin_user)
    db.session.commit()


if not os.path.exists('instance/db.db'):
    with app.app_context():
        db.create_all()
        create_default_user()
        print("Datenbank erstellt.")


@app.route('/')
def index():
    return render_template('index.html', app_name=app_name)


@app.route('/add_download', methods=['GET', 'POST'])
@requires_permission('author')
def add_download():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        file = request.files['file']
        if file and title and description:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER_DOWNLOADS'], filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            new_download = Downloads(title=title, description=description, file=filename)
            db.session.add(new_download)
            db.session.commit()
            flash('Download erfolgreich hinzugefügt')
            return redirect(url_for('index'))
        else:
            flash('Fehlende Informationen')
    return render_template('add_download.html')


@app.route('/download/<int:download_id>')
def download(download_id):
    requested_download = Downloads.query.get(download_id)
    if requested_download is None:
        return "Download not found", 404
    directory = os.path.join(app.root_path, app.config['UPLOAD_FOLDER_DOWNLOADS'])
    filename = requested_download.file
    try:
        return send_from_directory(directory, filename, as_attachment=True)
    except FileNotFoundError:
        return "File not found", 404


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_in_session = User.query.filter_by(username=username).first()
        if user_in_session and check_password_hash(user_in_session.password, password):
            session['username'] = user_in_session.username
            return redirect(url_for('index'))
        else:
            return render_template(login.html, app_name=app_name, error='Username or Password is wrong.')
    return render_template('login.html', app_name=app_name)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            return render_template('register.html', app_name=app_name, error='Username already exists.')
        else:
            new_user = User(username=username, password=generate_password_hash(password), leader=False, author=False)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html', app_name=app_name)


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))


@app.route('/projects')
def projects():
    all_projects = Project.query.all()
    return render_template('projects.html', projects=all_projects)


@app.route('/project/<int:project_id>')
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    return render_template('project_detail.html', project=project)


@app.route('/project/add', methods=['GET', 'POST'])
def add_project():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        project_link = request.form.get('project_link')
        download_option = request.form['download_option']
        download_id = None

        if download_option == 'existing':
            download_id = request.form['download_id']
        elif download_option == 'new':
            file = request.files['file']
            if file:
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER_DOWNLOADS'], filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                file.save(file_path)
                new_download = Downloads(title=title, description=description, file=filename)
                db.session.add(new_download)
                db.session.commit()
                download_id = new_download.id

        new_project = Project(title=title, description=description, download_id=download_id, project_link=project_link)
        db.session.add(new_project)
        db.session.commit()
        return redirect(url_for('projects'))

    downloads = Downloads.query.all()
    return render_template('add_project.html', downloads=downloads)


@app.route('/project/edit/<int:project_id>', methods=['GET', 'POST'])
@requires_permission('author')
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    downloads = Downloads.query.all()

    if request.method == 'POST':
        project.title = request.form['title']
        project.description = request.form['description']
        project.project_link = request.form.get('project_link')
        download_option = request.form['download_option']

        if download_option == 'existing':
            project.download_id = request.form['download_id']
        elif download_option == 'new':
            file = request.files['file']
            if file:
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER_DOWNLOADS'], filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                file.save(file_path)
                new_download = Downloads(title=project.title, description=project.description, file=filename)
                db.session.add(new_download)
                db.session.commit()
                project.download_id = new_download.id

        db.session.commit()
        return redirect(url_for('projects'))

    return render_template('edit_project.html', project=project, downloads=downloads)


@app.route('/news/add', methods=['GET', 'POST'])
@requires_permission('author')
def add_news():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        file = request.files['image']
        if file and title and description:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            new_news = News(title=title, description=description, image_path=filename, author_id=session['user_id'])
            db.session.add(new_news)
            db.session.commit()
            return redirect(url_for('list_news'))
    return render_template('add_news.html')


@app.route('/news')
def list_news():
    news_items = News.query.order_by(News.created_at.desc()).all()
    return render_template('list_news.html', news_items=news_items)


@app.route('/news/<int:news_id>')
def news_detail(news_id):
    news_item = News.query.get_or_404(news_id)
    return render_template('news_detail.html', news_item=news_item)


@app.route('/news/edit/<int:news_id>', methods=['GET', 'POST'])
@requires_permission('author')
def edit_news(news_id):
    news_item = News.query.get_or_404(news_id)

    if request.method == 'POST':
        news_item.title = request.form['title']
        news_item.description = request.form['description']
        file = request.files['image']
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER_PICTS'], filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            news_item.image_path = filename

        db.session.commit()
        return redirect(url_for('list_news'))

    return render_template('edit_news.html', news_item=news_item)


if __name__ == '__main__':
    app.run(debug=True)
