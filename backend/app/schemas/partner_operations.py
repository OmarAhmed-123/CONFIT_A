from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.app.schemas.money_types import PositiveMoney


class ProductEdit(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str | None = Field(None, min_length=1, max_length=255)
    title_ar: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, min_length=1, max_length=2000)
    description_ar: str | None = Field(None, min_length=1, max_length=2000)
    category_id: int | None = Field(None, gt=0)
    base_price: PositiveMoney | None = None
    material: str | None = Field(None, max_length=255)
    care_instructions: str | None = Field(None, max_length=500)
    color_family: str | None = Field(None, min_length=1, max_length=50)
    dominant_hex: str | None = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    style_tags: list[str] | None = Field(None, max_length=30)
    occasion_tags: list[str] | None = Field(None, max_length=30)
    status: Literal['draft', 'active', 'archived'] | None = None

    @model_validator(mode='after')
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError('Provide at least one editable field')
        for key in self.model_fields_set - {'material', 'care_instructions'}:
            if getattr(self, key) is None:
                raise ValueError('Required product values cannot be null')
        for key in ('style_tags', 'occasion_tags'):
            if any(not item.strip() or len(item)>80 for item in (getattr(self,key) or [])):
                raise ValueError('Tags must contain 1–80 characters')
        return self


class VariantEdit(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    size: str = Field(min_length=1, max_length=20)
    color: str = Field(min_length=1, max_length=50)
    color_hex: str = Field(default='#1B1F3B', pattern=r'^#[0-9A-Fa-f]{6}$')
    price_override: PositiveMoney | None = None


class VariantCreate(VariantEdit):
    sku_code: str = Field(pattern=r'^[A-Za-z0-9_-]{3,100}$')
