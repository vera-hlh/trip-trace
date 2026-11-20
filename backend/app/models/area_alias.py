"""景区别名：把变体名归一到规范名（按城市作用域）。"""
from sqlalchemy import Column, Integer, String, UniqueConstraint

from app.core.database import Base


class AreaAlias(Base):
    __tablename__ = "area_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String, nullable=False, index=True)
    alias_name = Column(String, nullable=False)
    canonical_name = Column(String, nullable=False)
    created_at = Column(String)

    __table_args__ = (
        UniqueConstraint("city", "alias_name", name="uq_area_alias_city_name"),
    )
