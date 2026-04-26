import os
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    create_engine,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///furniture_showroom.db")

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    sku = Column(String(100), unique=True, nullable=False)
    category = Column(String(100), nullable=False)
    purchase_price = Column(Float, nullable=False, default=0.0)
    sale_price = Column(Float, nullable=False, default=0.0)
    stock_quantity = Column(Integer, nullable=False, default=0)
    min_stock = Column(Integer, nullable=False, default=5)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    image_url = Column(String(500), nullable=True)
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    vendor = relationship("Vendor", back_populates="products")
    sale_items = relationship("SaleItem", back_populates="product")
    purchase_order_items = relationship("PurchaseOrderItem", back_populates="product")

class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    sale_date = Column(DateTime, default=datetime.utcnow)
    total_amount = Column(Float, nullable=False, default=0.0)
    discount = Column(Float, nullable=False, default=0.0)
    payment_method = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False, default="completed")

    customer = relationship("Customer", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale")

class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False, default=0.0)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="sale_items")

class Vendor(Base):
    __tablename__ = "vendors"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    balance_due = Column(Float, nullable=False, default=0.0)

    products = relationship("Product", back_populates="vendor")
    purchase_orders = relationship("PurchaseOrder", back_populates="vendor")

class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity_ordered = Column(Integer, nullable=False, default=0)
    quantity_received = Column(Integer, nullable=False, default=0)
    unit_price = Column(Float, nullable=False, default=0.0)

    purchase_order = relationship("PurchaseOrder", back_populates="items")
    product = relationship("Product", back_populates="purchase_order_items")

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    balance_receivable = Column(Float, nullable=False, default=0.0)

    sales = relationship("Sale", back_populates="customer")

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    order_date = Column(DateTime, default=datetime.utcnow)
    expected_delivery = Column(DateTime, nullable=True)
    status = Column(String(100), nullable=False, default="pending")
    notes = Column(Text, nullable=True)

    vendor = relationship("Vendor", back_populates="purchase_orders")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order")


def init_db():
    Base.metadata.create_all(bind=engine)
