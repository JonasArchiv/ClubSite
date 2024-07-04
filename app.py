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


class Downloads(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(100), nullable=False)
    file = db.Column(db.String(100), nullable=False)


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
@requires_permission('leader')
def add_download():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        file = request.files['file']
        if file and title and description:
            filename = secure_filename(file.filename)
            file_path = os.path.join('/static/downloads', filename)
            file.save(file_path)
            new_download = Downloads(title=title, description=description, file=filename)
            db.session.add(new_download)
            db.session.commit()
            flash('Download successfully added')
            return redirect(url_for('index'))
        else:
            flash('Missing information')

    return render_template('add_download.html')


@app.route('/download/<int:download_id>')
def download(download_id):
    download = Downloads.query.get(download_id)
    if download is None:
        return "Download not found", 404
    directory = '/static/downloads'
    filename = download.file
    file_path = os.path.join(directory, filename)
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


if __name__ == '__main__':
    app.run(debug=True)
