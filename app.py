import streamlit as st
import pandas as pd
import plotly.express as px
from utils.auth import login, require_authentication, logout
from utils.db import SessionLocal, Product, Sale, SaleItem, Vendor, Customer, PurchaseOrder, PurchaseOrderItem, init_db
from utils.invoice import build_invoice_pdf
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

init_db()

def normalize_number(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def normalize_record(record):
    return {k: normalize_number(v) for k, v in record.items()}

st.set_page_config(page_title="7 Star Furniture", page_icon="", layout="wide")

if not require_authentication():
    st.title("Furniture Showroom Login")
    st.markdown("Please enter your credentials to sign in.")
    status = login()
    if status is True:
        st.rerun()
    st.stop()

# Authenticated
logout()

page = st.sidebar.radio("Navigate", ["Dashboard", "Inventory", "Sales", "Vendors", "Customers", "Purchases", "Reports"])

if page == "Dashboard":
    st.title("Dashboard")
    st.subheader("Executive overview")

    with st.spinner("Loading dashboard metrics..."):
        session = SessionLocal()
        total_sales_today = session.query(func.count(Sale.id)).filter(Sale.status == "completed").scalar() or 0
        total_revenue = session.query(func.coalesce(func.sum(Sale.total_amount), 0)).scalar() or 0
        low_stock_products = session.query(Product).filter(Product.stock_quantity <= Product.min_stock).all()
        top_products = (
            session.query(Product.name, func.sum(SaleItem.quantity).label("sold"))
            .join(SaleItem, Product.id == SaleItem.product_id)
            .group_by(Product.name)
            .order_by(func.sum(SaleItem.quantity).desc())
            .limit(5)
            .all()
        )
        session.close()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Sales Today", total_sales_today)
    col2.metric("Revenue", f"Rs{normalize_number(total_revenue):,}")
    col3.metric("Low Stock Alerts", len(low_stock_products))
    col4.metric("Top Selling SKUs", len(top_products))

    st.markdown("---")
    if top_products:
        df_top = pd.DataFrame(top_products, columns=["product", "quantity_sold"])
        fig = px.bar(df_top, x="product", y="quantity_sold", title="Top Selling Products")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No sales data available yet.")

    if low_stock_products:
        low_data = [
            {
                "Product": p.name,
                "SKU": p.sku,
                "Stock": p.stock_quantity,
                "Min Stock": p.min_stock,
            }
            for p in low_stock_products
        ]
        st.subheader("Low Stock Alerts")
        st.dataframe(pd.DataFrame(low_data), use_container_width=True)
    else:
        st.success("No low stock alerts.")

elif page == "Inventory":
    st.title("Inventory Management")
    st.subheader("Product catalog and stock status")

    session = SessionLocal()
    vendors = session.scalars(select(Vendor)).all()
    products = session.scalars(select(Product)).all()

    button_col, _ = st.columns([4, 1])
    if button_col.button("+ Add product"):
        st.session_state["show_inventory_modal"] = True

    if st.session_state.get("show_inventory_modal", False):
        with st.expander("Add new product", expanded=True):
            name = st.text_input("Product name", key="inventory_name")
            sku = st.text_input("SKU / Barcode", key="inventory_sku")
            category = st.selectbox(
                "Category",
                ["Sofas", "Beds", "Dining", "Office Furniture", "Accessories"],
                key="inventory_category",
            )
            purchase_price = st.number_input(
                "Purchase price",
                min_value=0.0,
                step=1.0,
                format="%g",
                key="inventory_purchase_price",
            )
            sale_price = st.number_input(
                "Sale price",
                min_value=0.0,
                step=1.0,
                format="%g",
                key="inventory_sale_price",
            )
            stock_quantity = st.number_input("Stock quantity", min_value=0, step=1, key="inventory_stock_quantity")
            min_stock = st.number_input("Low stock threshold", min_value=0, step=1, value=5, key="inventory_min_stock")
            vendor_id = st.selectbox(
                "Vendor",
                [None] + [v.id for v in vendors],
                format_func=lambda x: "None" if x is None else next((v.name for v in vendors if v.id == x), "Unknown"),
                key="inventory_vendor_id",
            )
            location = st.text_input("Warehouse / Floor location", key="inventory_location")
            image_url = st.text_input("Image URL", key="inventory_image_url")
            if st.button("Save", key="save_product"):
                product = Product(
                    name=name,
                    sku=sku,
                    category=category,
                    purchase_price=purchase_price,
                    sale_price=sale_price,
                    stock_quantity=stock_quantity,
                    min_stock=min_stock,
                    vendor_id=vendor_id,
                    location=location,
                    image_url=image_url,
                )
                session.add(product)
                session.commit()
                st.session_state["show_inventory_modal"] = False
                st.success(f"Product '{name}' added.")
                st.rerun()

    if products:
        df_products = pd.DataFrame(
            [
                normalize_record(
                    {
                        "ID": p.id,
                        "Name": p.name,
                        "SKU": p.sku,
                        "Category": p.category,
                        "Stock": p.stock_quantity,
                        "Min Stock": p.min_stock,
                        "Purchase Price": p.purchase_price,
                        "Sale Price": p.sale_price,
                        "Vendor": p.vendor.name if p.vendor else "—",
                        "Location": p.location or "—",
                    }
                )
                for p in products
            ]
        )
        st.dataframe(df_products, use_container_width=True)
    else:
        st.info("No products available. Add inventory to get started.")

    session.close()

elif page == "Sales":
    st.title("Sales / POS")

    session = SessionLocal()
    products = session.scalars(select(Product)).all()
    customers = session.scalars(select(Customer)).all()

    if "cart" not in st.session_state:
        st.session_state.cart = []

    # =========================
    # SEARCH
    # =========================
    search_term = st.text_input(
        "Search Product by Name / SKU",
        placeholder="Search product..."
    )

    filtered_products = []

    if len(search_term.strip()) >= 2:
        filtered_products = [
            p for p in products
            if search_term.lower() in p.name.lower()
            or search_term.lower() in (p.sku or "").lower()
        ]

    if filtered_products:
        st.markdown("### Search Results")

        header = st.columns([4, 2, 2, 2, 1])
        header[0].markdown("**Product**")
        header[1].markdown("**SKU**")
        header[2].markdown("**Price**")
        header[3].markdown("**Stock**")
        header[4].markdown("**Action**")

        for product in filtered_products:
            cols = st.columns([4, 2, 2, 2, 1])

            cols[0].write(product.name)
            cols[1].write(product.sku or "-")
            cols[2].write(f"Rs{normalize_number(product.sale_price):,}")
            cols[3].write(product.stock_quantity)

            if cols[4].button("Add", key=f"add_{product.id}"):

                existing = next(
                    (item for item in st.session_state.cart
                     if item["product_id"] == product.id),
                    None
                )

                if existing:
                    if existing["qty"] + 1 > product.stock_quantity:
                        st.error("Stock exceeded")
                    else:
                        existing["qty"] += 1
                        existing["subtotal"] = existing["qty"] * existing["price"]
                else:
                    st.session_state.cart.append({
                        "product_id": product.id,
                        "name": product.name,
                        "price": float(product.sale_price),
                        "qty": 1,
                        "subtotal": float(product.sale_price)
                    })

                st.rerun()

    elif search_term:
        st.warning("No matching products found.")

    # =========================
    # CART SECTION
    # =========================
    st.markdown("---")
    st.markdown("## Cart")

    if st.session_state.cart:

        subtotal = 0

        header = st.columns([4, 2, 2, 2, 1])
        header[0].markdown("**Product**")
        header[1].markdown("**Price**")
        header[2].markdown("**Qty**")
        header[3].markdown("**Subtotal**")
        header[4].markdown("**Remove**")

        for idx, item in enumerate(st.session_state.cart):
            subtotal += item["subtotal"]
            
            # Get product stock for max quantity validation
            product = session.get(Product, item["product_id"])
            max_qty = product.stock_quantity if product else 999

            cols = st.columns([4, 2, 2, 2, 1])

            cols[0].write(item["name"])
            cols[1].write(f"Rs{normalize_number(item['price']):,}")
            new_qty = cols[2].number_input(
                "Qty",
                min_value=1,
                max_value=max_qty,
                value=item["qty"],
                key=f"qty_{idx}",
                label_visibility="collapsed"
            )
            if new_qty != item["qty"]:
                item["qty"] = new_qty
                item["subtotal"] = item["qty"] * item["price"]
                st.rerun()
            cols[3].write(f"Rs{normalize_number(item['subtotal']):,}")

            if cols[4].button("X", key=f"remove_{idx}"):
                st.session_state.cart.pop(idx)
                st.rerun()

        st.markdown("---")

        checkout_cols = st.columns(3)

        customer_id = checkout_cols[0].selectbox(
            "Customer",
            [None] + [c.id for c in customers],
            format_func=lambda x: (
                "Walk-in"
                if x is None
                else next((c.name for c in customers if c.id == x), "Unknown")
            )
        )

        discount = checkout_cols[1].number_input(
            "Discount",
            min_value=0.0,
            value=0.0,
            step=1.0
        )

        payment_method = checkout_cols[2].selectbox(
            "Payment",
            ["Cash", "Card", "Transfer", "Mobile Wallet"]
        )

        grand_total = max(subtotal - discount, 0)

        st.metric("Total", f"Rs{normalize_number(grand_total):,}")

        # =========================
        # COMPLETE SALE
        # =========================
        if st.button("Complete Sale", use_container_width=True):

            if not st.session_state.cart:
                st.error("Cart is empty")
                st.stop()

            # Validate stock first
            for item in st.session_state.cart:
                product = session.get(Product, item["product_id"])
                if product.stock_quantity < item["qty"]:
                    st.error(f"Insufficient stock for {product.name}")
                    session.rollback()
                    st.stop()

            sale = Sale(
                customer_id=customer_id,
                sale_date=datetime.utcnow(),
                total_amount=grand_total,
                discount=discount,
                payment_method=payment_method,
                status="completed"
            )

            session.add(sale)
            session.commit()

            invoice_rows = []

            for item in st.session_state.cart:
                product = session.get(Product, item["product_id"])

                product.stock_quantity -= item["qty"]

                session.add(SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    quantity=item["qty"],
                    unit_price=item["price"]
                ))

                invoice_rows.append((product, item["qty"]))

            session.commit()

            pdf_bytes = build_invoice_pdf(sale, invoice_rows)

            st.session_state["latest_invoice_pdf"] = pdf_bytes
            st.session_state["latest_invoice_name"] = f"invoice_{sale.id}.pdf"

            st.session_state.cart = []

            st.success(f"Sale #{sale.id} completed.")
            st.rerun()

    else:
        st.info("Cart is empty.")

    # =========================
    # INVOICE DOWNLOAD
    # =========================
    if st.session_state.get("latest_invoice_pdf"):
        st.download_button(
            "Download Invoice",
            st.session_state["latest_invoice_pdf"],
            file_name=st.session_state["latest_invoice_name"],
            mime="application/pdf"
        )

    session.close()

elif page == "Vendors":
    st.title("Vendor Management")
    st.subheader("Supplier directory")

    session = SessionLocal()
    vendors = session.scalars(select(Vendor)).all()

    button_col, _ = st.columns([4, 1])
    if button_col.button("+ Add vendor"):
        st.session_state["show_vendor_modal"] = True

    if st.session_state.get("show_vendor_modal", False):
        with st.expander("Add vendor", expanded=True):
            name = st.text_input("Vendor name", key="vendor_name")
            phone = st.text_input("Phone", key="vendor_phone")
            email = st.text_input("Email", key="vendor_email")
            address = st.text_area("Address", key="vendor_address")
            if st.button("Save vendor", key="save_vendor"):
                vendor = Vendor(name=name, phone=phone, email=email, address=address)
                session.add(vendor)
                session.commit()
                st.session_state["show_vendor_modal"] = False
                st.success(f"Vendor '{name}' added.")
                st.rerun()

    if vendors:
        df_vendors = pd.DataFrame(
            [
                normalize_record(
                    {
                        "ID": v.id,
                        "Name": v.name,
                        "Phone": v.phone,
                        "Email": v.email,
                        "Address": v.address,
                        "Balance Due": v.balance_due,
                    }
                )
                for v in vendors
            ]
        )
        st.dataframe(df_vendors, use_container_width=True)
    else:
        st.info("No vendors found. Add one to start tracking purchase orders.")

    session.close()

elif page == "Customers":
    st.title("Customer Management")
    st.subheader("CRM-lite customer list")

    session = SessionLocal()
    customers = session.scalars(select(Customer)).all()

    button_col, _ = st.columns([4, 1])
    if button_col.button("+ Add customer"):
        st.session_state["show_customer_modal"] = True

    if st.session_state.get("show_customer_modal", False):
        with st.expander("Add customer", expanded=True):
            name = st.text_input("Customer name", key="customer_name")
            phone = st.text_input("Phone", key="customer_phone")
            email = st.text_input("Email", key="customer_email")
            address = st.text_area("Delivery address", key="customer_address")
            if st.button("Save customer", key="save_customer"):
                customer = Customer(name=name, phone=phone, email=email, address=address)
                session.add(customer)
                session.commit()
                st.session_state["show_customer_modal"] = False
                st.success(f"Customer '{name}' added.")
                st.rerun()

    if customers:
        df_customers = pd.DataFrame(
            [
                normalize_record(
                    {
                        "ID": c.id,
                        "Name": c.name,
                        "Phone": c.phone,
                        "Email": c.email,
                        "Address": c.address,
                        "Balance Receivable": c.balance_receivable,
                    }
                )
                for c in customers
            ]
        )
        st.dataframe(df_customers, use_container_width=True)
    else:
        st.info("No customers registered yet.")

    session.close()

elif page == "Purchases":
    st.title("Purchase Management")
    st.subheader("Purchase orders and receipt workflow")

    session = SessionLocal()
    vendors = session.scalars(select(Vendor)).all()
    products = session.scalars(select(Product)).all()
    purchase_orders = session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.order_date.desc())).all()

    button_col, _ = st.columns([4, 1])
    if button_col.button("+ New purchase order"):
        st.session_state["show_purchase_modal"] = True

    if st.session_state.get("show_purchase_modal", False):
        with st.expander("Create Purchase Order", expanded=True):
            vendor_id = st.selectbox(
                "Vendor",
                [None] + [v.id for v in vendors],
                format_func=lambda x: "Select vendor" if x is None else next((v.name for v in vendors if v.id == x), "Unknown"),
                key="po_vendor_id",
            )
            expected_delivery = st.date_input(
                "Expected delivery date",
                value=datetime.utcnow().date(),
                key="po_expected_delivery",
            )
            notes = st.text_area("Notes", key="po_notes")
            num_lines = st.number_input("Line items", min_value=1, max_value=8, value=2, key="po_num_lines")
            order_lines = []
            for index in range(num_lines):
                cols = st.columns([3, 1, 1])
                product_id = cols[0].selectbox(
                    f"Product #{index + 1}",
                    [None] + [p.id for p in products],
                    key=f"po_product_{index}",
                    format_func=lambda x: "Select product" if x is None else next((p.name for p in products if p.id == x), "Unknown"),
                )
                quantity = cols[1].number_input(f"Qty #{index + 1}", min_value=0, step=1, key=f"po_qty_{index}")
                unit_price = cols[2].number_input(
                    f"Unit price #{index + 1}",
                    min_value=0.0,
                    step=1.0,
                    format="%g",
                    key=f"po_price_{index}",
                )
                if product_id and quantity > 0:
                    order_lines.append((product_id, quantity, unit_price))

            if st.button("Save purchase order", key="save_purchase_order"):
                if vendor_id is None:
                    st.error("Please select a vendor.")
                elif not order_lines:
                    st.error("Add at least one product line item.")
                else:
                        po = PurchaseOrder(
                            vendor_id=vendor_id,
                            order_date=datetime.utcnow(),
                            expected_delivery=expected_delivery,
                            status="pending",
                            notes=notes,
                        )
                        session.add(po)
                        session.commit()
                        for product_id, quantity, unit_price in order_lines:
                            session.add(
                                PurchaseOrderItem(
                                    purchase_order_id=po.id,
                                    product_id=product_id,
                                    quantity_ordered=quantity,
                                    quantity_received=0,
                                    unit_price=unit_price,
                                )
                            )
                        session.commit()
                        st.session_state["show_purchase_modal"] = False
                        st.success(f"Purchase order #{po.id} created.")
                        st.rerun()

    if purchase_orders:
        df_po = pd.DataFrame(
            [
                {
                    "PO": po.id,
                    "Vendor": po.vendor.name if po.vendor else "Unknown",
                    "Date": po.order_date,
                    "Delivery": po.expected_delivery,
                    "Status": po.status,
                }
                for po in purchase_orders
            ]
        )
        st.dataframe(df_po, use_container_width=True)

        for po in purchase_orders:
            with st.expander(f"PO #{po.id} — {po.vendor.name if po.vendor else 'Unknown'} — {po.status}"):
                st.write(f"Expected delivery: {po.expected_delivery}")
                st.write(f"Notes: {po.notes or '—'}")
                if po.items:
                    item_rows = [
                        normalize_record(
                            {
                                "Product": item.product.name,
                                "Ordered": item.quantity_ordered,
                                "Received": item.quantity_received,
                                "Outstanding": item.quantity_ordered - item.quantity_received,
                                "Unit Price": item.unit_price,
                            }
                        )
                        for item in po.items
                    ]
                    st.dataframe(pd.DataFrame(item_rows), use_container_width=True)

                if po.status != "completed":
                    receive_quantities = {}
                    for item in po.items:
                        outstanding = item.quantity_ordered - item.quantity_received
                        if outstanding > 0:
                            receive_quantities[item.id] = st.number_input(
                                f"Receive {item.product.name}",
                                min_value=0,
                                max_value=outstanding,
                                value=0,
                                step=1,
                                key=f"receive_{po.id}_{item.id}",
                            )
                    if st.button("Receive inventory", key=f"receive_inventory_{po.id}"):
                        total_received = 0
                        for item_id, qty in receive_quantities.items():
                            if qty > 0:
                                item = session.get(PurchaseOrderItem, item_id)
                                item.quantity_received += qty
                                item.product.stock_quantity += qty
                                total_received += qty
                        if total_received > 0:
                            session.commit()
                            incomplete = any(
                                item.quantity_received < item.quantity_ordered for item in po.items
                            )
                            po.status = "partial" if incomplete else "completed"
                            session.commit()
                            st.success(f"Received {total_received} units into inventory.")
                            st.rerun()
                        else:
                            st.info("No items were received. Enter quantities to update stock.")
                else:
                    st.success("This purchase order is fully received.")
    else:
        st.info("No purchase orders available. Create one to start the receiving workflow.")

    session.close()

elif page == "Reports":
    st.title("Reports & Analytics")
    st.subheader("Sales, inventory, and product performance")

    session = SessionLocal()

    sales_by_period = (
        session.query(func.strftime("%Y-%m", Sale.sale_date).label("period"), func.sum(Sale.total_amount).label("revenue"))
        .group_by("period")
        .order_by("period")
        .all()
    )
    product_performance = (
        session.query(Product.name, func.sum(SaleItem.quantity).label("sold"))
        .join(SaleItem, Product.id == SaleItem.product_id)
        .group_by(Product.name)
        .order_by(func.sum(SaleItem.quantity).desc())
        .limit(10)
        .all()
    )

    # Get all sales for history table with eager loading
    all_sales = session.query(Sale).options(
        selectinload(Sale.items).selectinload(SaleItem.product),
        selectinload(Sale.customer)
    ).order_by(Sale.sale_date.desc()).all()

    # Build sales history data while session is still open
    sales_data = []
    if all_sales:
        for sale in all_sales:
            items_list = ", ".join([f"{item.quantity}x {item.product.name}" for item in sale.items])
            sales_data.append(
                normalize_record(
                    {
                        "ID": sale.id,
                        "Date": sale.sale_date,
                        "Customer": sale.customer.name if sale.customer else "Walk-in",
                        "Items": items_list,
                        "Subtotal": sale.total_amount + sale.discount,
                        "Discount": sale.discount,
                        "Total": sale.total_amount,
                        "Payment": sale.payment_method,
                        "Status": sale.status,
                    }
                )
            )

    session.close()

    if sales_by_period:
        df_sales = pd.DataFrame(sales_by_period, columns=["period", "revenue"])
        fig = px.line(df_sales, x="period", y="revenue", title="Sales by Period")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No sales history to display.")

    if product_performance:
        df_perf = pd.DataFrame(product_performance, columns=["product", "sold"])
        fig2 = px.bar(df_perf, x="product", y="sold", title="Product Performance")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No product performance data yet.")

    # =========================
    # SALES HISTORY TABLE
    # =========================
    st.markdown("---")
    st.subheader("Sales History")

    if sales_data:
        df_history = pd.DataFrame(sales_data)
        st.dataframe(df_history, use_container_width=True)

        # CSV Download
        csv_data = df_history.to_csv(index=False)
        st.download_button(
            label="Download Sales History (CSV)",
            data=csv_data,
            file_name="sales_history.csv",
            mime="text/csv"
        )
    else:
        st.info("No sales records available.")

    # =========================
    # DATABASE EXPORT
    # =========================
    st.markdown("---")
    st.subheader("Database Export")

    export_session = SessionLocal()

    # Prepare export data
    export_data = {}

    # Products
    products_list = export_session.query(Product).all()
    export_data["products"] = pd.DataFrame([
        normalize_record({
            "ID": p.id,
            "Name": p.name,
            "SKU": p.sku,
            "Category": p.category,
            "Purchase Price": p.purchase_price,
            "Sale Price": p.sale_price,
            "Stock": p.stock_quantity,
            "Min Stock": p.min_stock,
            "Vendor": p.vendor.name if p.vendor else "",
            "Location": p.location or "",
        })
        for p in products_list
    ])

    # Customers
    customers_list = export_session.query(Customer).all()
    export_data["customers"] = pd.DataFrame([
        normalize_record({
            "ID": c.id,
            "Name": c.name,
            "Phone": c.phone,
            "Email": c.email,
            "Address": c.address,
        })
        for c in customers_list
    ])

    # Vendors
    vendors_list = export_session.query(Vendor).all()
    export_data["vendors"] = pd.DataFrame([
        normalize_record({
            "ID": v.id,
            "Name": v.name,
            "Phone": v.phone,
            "Email": v.email,
            "Address": v.address,
        })
        for v in vendors_list
    ])

    # Sales (detailed)
    sales_list = export_session.query(Sale).all()
    export_data["sales"] = pd.DataFrame([
        normalize_record({
            "ID": s.id,
            "Date": s.sale_date,
            "Customer": s.customer.name if s.customer else "Walk-in",
            "Subtotal": s.total_amount + s.discount,
            "Discount": s.discount,
            "Total": s.total_amount,
            "Payment": s.payment_method,
            "Status": s.status,
        })
        for s in sales_list
    ])

    export_session.close()

    col1, col2 = st.columns(2)

    # Individual CSV downloads
    with col1:
        st.markdown("**Download Individual Tables:**")
        for table_name, df in export_data.items():
            csv_data = df.to_csv(index=False)
            st.download_button(
                label=f"📥 {table_name.title()}",
                data=csv_data,
                file_name=f"{table_name}.csv",
                mime="text/csv",
                key=f"download_{table_name}"
            )

    # Combined CSV download
    with col2:
        st.markdown("**Download All Data:**")
        import io
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for table_name, df in export_data.items():
                df.to_excel(writer, sheet_name=table_name, index=False)
        output.seek(0)
        st.download_button(
            label="📊 All Tables (Excel)",
            data=output.getvalue(),
            file_name="database_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
