import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models.user import db, User, Product
from blockchain.blockchain import LightBlockchain
from iot.iot_sensor import IoTSensor

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-12345'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///traceability.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# Initialize Blockchain
blockchain = LightBlockchain()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('signup'))

        new_user = User(username=username, email=email, full_name=full_name, role='user')
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! Please login.')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        admin_key = request.form.get('admin_key')

        if admin_key != 'ADMIN123': # Simple key for demo
            flash('Invalid Admin Secret Key')
            return redirect(url_for('admin_register'))

        if User.query.filter_by(username=username).first():
            flash('Admin username already exists')
            return redirect(url_for('admin_register'))

        new_admin = User(username=username, email=email, role='admin')
        new_admin.set_password(password)
        db.session.add(new_admin)
        db.session.commit()
        flash('Admin registered successfully!')
        return redirect(url_for('login'))
    return render_template('admin_register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        products = Product.query.all()
        return render_template('admin_dashboard.html', products=products)
    else:
        # For a simple demo, show few products
        products = Product.query.limit(5).all()
        return render_template('user_dashboard.html', products=products)

@app.route('/product/add', methods=['POST'])
@login_required
def add_product():
    if current_user.role != 'admin':
        return redirect(url_for('dashboard'))

    p_id = request.form.get('product_id')
    name = request.form.get('name')
    category = request.form.get('category')
    origin = request.form.get('origin')

    new_p = Product(product_id=p_id, name=name, category=category, origin=origin, harvest_date=datetime.now())
    db.session.add(new_p)
    db.session.commit()

    # Create Genesis entry in blockchain for this product
    blockchain.add_block({
        "product_id": p_id,
        "name": name,
        "event": "HARVESTED",
        "origin": origin,
        "category": category,
        "details": "Initial product registration on blockchain"
    })

    flash(f"Product {p_id} added to ledger.")
    return redirect(url_for('dashboard'))

@app.route('/product/trace/<product_id>')
def trace_product(product_id):
    history = blockchain.get_product_traceability(product_id)
    product = Product.query.filter_by(product_id=product_id).first()

    # Simulate real-time IoT update if not tracking
    if not any(h['data'].get('event') == 'TRANSIT' for h in history):
        sensor = IoTSensor(product_id, product.category if product else "Produce")
        reading = sensor.read_sensors()
        reading['event'] = 'TRANSIT'
        blockchain.add_block(reading)
        history = blockchain.get_product_traceability(product_id)

    return render_template('traceability.html', history=history, product=product)

@app.route('/api/sensor/<product_id>')
def get_sensor_data(product_id):
    product = Product.query.filter_by(product_id=product_id).first()
    if not product:
        return jsonify({"error": "Not found"}), 404
    sensor = IoTSensor(product_id, product.category)
    return jsonify(sensor.read_sensors())

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)