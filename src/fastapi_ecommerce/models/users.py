from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fastapi_ecommerce.database import Base
from fastapi_ecommerce.models.orders import Order


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True,
                                       nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String, default="buyer")
    products: Mapped[list["Product"]] = relationship("Product",
                                                     back_populates="seller")
    reviews: Mapped[list["Review"]] = relationship("Review",
                                                   back_populates="buyer")
    cart_items: Mapped[list["CartItem"]] = relationship("CartItem",
                                                        back_populates="user",
                                                        cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship("Order",
                                                 back_populates="user",
                                                 cascade="all, delete-orphan")
