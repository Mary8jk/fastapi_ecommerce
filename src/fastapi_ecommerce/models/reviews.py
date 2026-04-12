from sqlalchemy import (CheckConstraint,
                        String,
                        Boolean,
                        Integer,
                        DateTime,
                        ForeignKey
                        )
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from fastapi_ecommerce.database import Base


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"),
                                         nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"),
                                            nullable=False)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    comment_date: Mapped[datetime] = mapped_column(DateTime,
                                                   default=datetime.now)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    buyer: Mapped["User"] = relationship("User",
                                         back_populates='reviews')
    product: Mapped["Product"] = relationship("Product",
                                              back_populates='reviews')

    __table_args__ = (
        CheckConstraint('grade >=1 and grade <= 5', name='grade_check'),
    )
