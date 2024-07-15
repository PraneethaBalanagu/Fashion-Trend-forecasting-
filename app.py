from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from pytrends.request import TrendReq
import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import time

# Initialize Flask application
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure secret key

# Configuration for SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'mssql+pyodbc://@DESKTOP-DI486IP/trend?driver=ODBC+Driver+17+for+SQL+Server'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Define User model
class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

# Routes

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = Users.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Check if username already exists
        existing_user = Users.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different username.', 'error')
        else:
            # Create new user
            new_user = Users(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('Signup successful! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/products')
def products():
    # Return contents of products.json file
    with open(os.path.join(app.root_path, 'static', 'products.json')) as f:
        products_data = json.load(f)
    return jsonify(products_data)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' in session:
        if request.method == 'POST':
            # Handle file upload
            file = request.files['file']
            if file and file.filename.endswith('.json'):
                file_path = os.path.join('uploads', file.filename)
                file.save(file_path)
                return redirect(url_for('analysis', filename=file.filename))
            else:
                flash('Invalid file format. Please upload a JSON file.', 'error')
        return render_template('dashboard.html', username=session['username'])
    return redirect(url_for('login'))

@app.route('/analysis/<filename>')
def analysis(filename):
    file_path = os.path.join('uploads', filename)
    
    # Load data from JSON file
    try:
        with open(file_path) as f:
            data = json.load(f)
    except FileNotFoundError:
        flash('File not found. Please upload a valid JSON file.', 'error')
        return redirect(url_for('dashboard'))
    except json.JSONDecodeError:
        flash('Invalid JSON file. Please upload a valid JSON file.', 'error')
        return redirect(url_for('dashboard'))

    # Convert data to DataFrame
    df = pd.DataFrame(data['products'])

    # Calculate growth rate
    df['growth_rate'] = (df['sales_month2'] - df['sales_month1']) / df['sales_month1']

    # Project future sales (simple linear projection)
    df['projected_sales'] = df['sales_month2'] * (1 + df['growth_rate'])**12

    # Check Google Trends
    pytrends = TrendReq(hl='en-US', tz=360)
    trending_products = []

    for index, row in df.iterrows():
        try:
            pytrends.build_payload([row['name']], cat=0, timeframe='today 12-m', geo='', gprop='')
            trends_data = pytrends.interest_over_time()
            if not trends_data.empty and trends_data[row['name']].iloc[-1] > 0:
                trending_products.append(row['name'])
        except Exception as e:
            flash(f'Error checking Google Trends for {row["name"]}: {str(e)}', 'error')
            time.sleep(60)  # wait for a minute before retrying

    # Plotting (simple example)
    fig, ax = plt.subplots()
    for _, row in df.iterrows():
        months = ['Month 1', 'Month 2', 'Projected (1 year)']
        sales = [row['sales_month1'], row['sales_month2'], row['projected_sales']]
        ax.plot(months, sales, marker='o', label=row['name'])

    plt.xlabel('Month')
    plt.ylabel('Sales')
    plt.title('Sales and Projected Sales')
    plt.legend()
    
    # Ensure 'static' directory exists
    static_dir = os.path.join(app.root_path, 'static')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    
    plot_filename = 'plot.png'
    plot_path = os.path.join(static_dir, plot_filename)
    plt.savefig(plot_path)

    return render_template('analysis.html', plot_url=url_for('static', filename=plot_filename), trending_products=trending_products)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    with app.app_context():
        db.create_all()
    app.run(debug=True)
