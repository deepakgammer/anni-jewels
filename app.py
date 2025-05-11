from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.utils import secure_filename
from models import db, Product, Order
from datetime import timedelta
from urllib.parse import quote
from reportlab.pdfgen import canvas
from flask import make_response
from fpdf import FPDF
from flask import send_file
from pytz import timezone
from datetime import datetime
import io
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///products.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.secret_key = "anni_secret_key"
app.permanent_session_lifetime = timedelta(days=7)

db.init_app(app)

with app.app_context():
    db.create_all()

@app.route("/", methods=["GET"])
def home():
    search = request.args.get('search', '').lower()
    if search:
        products = Product.query.filter(
            (Product.name.ilike(f"%{search}%")) | 
            (Product.code.ilike(f"%{search}%"))
        ).all()
    else:
        products = Product.query.all()
    return render_template("index.html", products=products, search=search)

@app.route('/admin/delete_order/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()
    flash("✅ Order deleted successfully.")
    return redirect(url_for('admin_orders'))  # ✅ Redirect to admin orders page



@app.route('/admin/add', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        code = request.form['code']
        image = request.files['image']
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        new_product = Product(name=name, price=price, image=filename, code=code)
        db.session.add(new_product)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('admin_add.html')

@app.route("/admin/dashboard")
def admin_dashboard():
    products = Product.query.all()
    return render_template("admin_dashboard.html", products=products)

@app.route("/admin/delete/<int:id>", methods=["POST"])
def delete_product(id):
    product = Product.query.get(id)
    if product:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], product.image)
        if os.path.exists(image_path):
            os.remove(image_path)
        db.session.delete(product)
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/edit/<int:id>", methods=["GET", "POST"])
def edit_product(id):
    product = Product.query.get(id)
    if request.method == "POST":
        product.name = request.form["name"]
        product.price = request.form["price"]
        product.code = request.form["code"]
        db.session.commit()
        return redirect(url_for('admin_dashboard'))
    return render_template("edit_product.html", product=product)

@app.route("/remove_from_cart/<int:product_id>")
def remove_from_cart(product_id):
    cart = session.get("cart", [])
    if product_id in cart:
        cart.remove(product_id)
        session["cart"] = cart
    return redirect(url_for("view_cart"))

# Modify add_to_cart route
@app.route("/add_to_cart/<int:product_id>", methods=["GET", "POST"])
def add_to_cart(product_id):
    cart = session.get("cart", {})

    # Handle quantity (default to 1 if not specified)
    qty = int(request.form.get("quantity", 1))

    if str(product_id) in cart:
        cart[str(product_id)] += qty
    else:
        cart[str(product_id)] = qty

    session["cart"] = cart
    flash("✅ Product added to cart successfully!")
    return redirect(url_for("home"))


@app.route("/cart")
def view_cart():
    cart = session.get("cart", {})
    product_ids = list(map(int, cart.keys()))
    products = Product.query.filter(Product.id.in_(product_ids)).all()
    total = sum([p.price * cart[str(p.id)] for p in products])
    return render_template("cart.html", products=products, quantities=cart, total=total)

@app.route("/order")
def whatsapp_order():
    cart = session.get("cart", [])
    products = Product.query.filter(Product.id.in_(cart)).all()
    total = sum([p.price for p in products])

    message = "Hello! I want to order:\n"
    for p in products:
        message += f"- {p.name} (₹{p.price}) [Code: {p.code}]\n"
    message += f"\nTotal: ₹{total}"

    encoded_message = quote(message)
    whatsapp_url = f"https://web.whatsapp.com/send?phone=917708391596&text={encoded_message}"

    return redirect(whatsapp_url)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart = session.get('cart', {})  # now a dict with {product_id: quantity}
    product_ids = list(map(int, cart.keys()))
    products = Product.query.filter(Product.id.in_(product_ids)).all()

    # Calculate total using quantity
    total = sum([p.price * cart[str(p.id)] for p in products])

    if request.method == 'POST':
        # Include quantity in product list (e.g. Ring [Code: R1] x2)
        product_details = ", ".join([
            f"{p.name} [Code: {p.code}] x{cart[str(p.id)]}"
            for p in products
        ])

        new_order = Order(
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            whatsapp=request.form['whatsapp'],
            address=request.form['address'],
            country=request.form['country'],
            locality=request.form['locality'],
            city=request.form['city'],
            state=request.form['state'],
            pincode=request.form['pincode'],
            email=request.form['email'],
            products=product_details,
            total_price=total
        )
        db.session.add(new_order)
        db.session.commit()
        session['cart'] = {}
        return redirect(url_for('order_success'))

    return render_template('checkout.html', products=products, total=total, quantities=cart)



@app.route('/order-success')
def order_success():
    return "Thank you for your order! We'll contact you on WhatsApp shortly."

@app.route("/admin_orders", methods=["GET", "POST"])
def admin_orders():
    search = request.args.get('search', '').lower()
    india = timezone("Asia/Kolkata")

    if search:
        orders = Order.query.filter(
            (Order.first_name.ilike(f"%{search}%")) |
            (Order.last_name.ilike(f"%{search}%")) |
            (Order.whatsapp.ilike(f"%{search}%")) |
            (Order.email.ilike(f"%{search}%"))
        ).all()
    else:
        orders = Order.query.all()

    # Convert time to IST
    for order in orders:
        if order.created_at:
            order.created_at = order.created_at.astimezone(india)

    return render_template("admin_orders.html", orders=orders, search=search)

    return render_template("admin_orders.html", orders=orders)
@app.route('/generate_bill/<int:order_id>')
def generate_bill(order_id):
    order = Order.query.get_or_404(order_id)

    safe_name = order.first_name.replace(" ", "_")
    filename = f"Bill_{safe_name}_{order.id}.pdf"
    pdf_path = os.path.join("static", "bills", filename)
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # ---- FROM Address on top-right ----
    pdf.set_font("Arial", 'B', 12)
    pdf.set_xy(140, 25)
    pdf.multi_cell(60, 8, "From:\nPrincess Collection\nNo:118\nSv Nagar\nPerumalpattu\nThiruvallur - 602024", align='R')

    # ---- Title ----
    pdf.set_xy(10, 10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(100, 10, "Princess Collection - Customer Bill", ln=True)

    # ---- Logo ----
    try:
        pdf.image("static/logo.png", x=10, y=20, w=30)
    except:
        pass  # Skip if logo not found

    pdf.ln(30)

    # ---- Billing To ----
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, "Bill To:", ln=True)
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 8, f"{order.first_name} {order.last_name}", ln=True)
    pdf.cell(100, 8, f"{order.address}, {order.locality}", ln=True)
    pdf.cell(100, 8, f"{order.city}, {order.state} - {order.pincode}", ln=True)
    pdf.cell(100, 8, f"{order.country}", ln=True)
    pdf.cell(100, 8, f"WhatsApp: {order.whatsapp}", ln=True)
    pdf.cell(100, 8, f"Email: {order.email}", ln=True)
    pdf.ln(10)

    # ---- Order Info ----
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, "Order Information:", ln=True)
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 8, f"Order ID: {order.id}", ln=True)
    pdf.cell(100, 8, f"Payment Method: Online", ln=True)
    pdf.ln(10)

    # ---- Product Table ----
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(10, 10, "S.No", 1)
    pdf.cell(80, 10, "Product", 1)
    pdf.cell(30, 10, "Qty", 1)
    pdf.cell(30, 10, "Unit Price", 1)
    pdf.cell(40, 10, "Total", 1)
    pdf.ln()

    # --- Product Rows ---
    pdf.set_font("Arial", '', 12)
    product_lines = [p.strip() for p in order.products.split(",")]

    from models import Product
    total_price = 0

    for i, product_line in enumerate(product_lines, start=1):
        try:
            # Format: Product Name [Code: XYZ] x2
            name_part = product_line.split("[")[0].strip()
            code_part = product_line.split("Code:")[1].split("]")[0].strip()
            qty_part = int(product_line.split("x")[-1].strip())

            db_product = Product.query.filter_by(code=code_part).first()
            price = db_product.price if db_product else 0
            line_total = price * qty_part
        except:
            name_part, code_part, qty_part, price, line_total = "-", "-", 1, 0, 0

        total_price += line_total

        pdf.cell(10, 10, str(i), 1)
        pdf.cell(80, 10, f"{name_part} [Code: {code_part}]", 1)
        pdf.cell(30, 10, str(qty_part), 1)
        pdf.cell(30, 10, f"Rs. {price}", 1)
        pdf.cell(40, 10, f"Rs. {line_total}", 1)
        pdf.ln()

    # ---- Summary ----
    pdf.ln(5)
    pdf.cell(150, 10, "Subtotal", 0, 0, 'R')
    pdf.cell(40, 10, f"Rs. {total_price}", 0, 1, 'R')

    pdf.cell(150, 10, "Total", 0, 0, 'R')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(40, 10, f"Rs. {total_price}", 0, 1, 'R')

    # ---- Footer ----
    pdf.set_y(-30)
    pdf.set_font("Arial", 'I', 11)
    pdf.cell(0, 10, "Thank you for shopping with us!", 0, 0, 'C')

    pdf.output(pdf_path)
    return send_file(pdf_path, as_attachment=True)

@app.route("/update_quantity/<int:product_id>", methods=["POST"])
def update_quantity(product_id):
    cart = session.get("cart", {})
    qty = int(request.form.get("quantity", 1))

    if qty > 0:
        cart[str(product_id)] = qty
    else:
        cart.pop(str(product_id), None)  # If qty is 0, remove it

    session["cart"] = cart
    flash("🛍️ Cart updated successfully!")
    return redirect(url_for("view_cart"))



if __name__ == '__main__':
    app.run(debug=True)
