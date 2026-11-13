from datetime import date, datetime
from typing import Any
from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.base import TimestampMixin, new_id, now_utc
class FullInventory(TimestampMixin, Base):
 __tablename__='ml_full_inventories'
 __table_args__=(UniqueConstraint('account_id','inventory_id',name='uq_full_inventory_account_inventory'),)
 id: Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
 account_id: Mapped[str]=mapped_column(ForeignKey('marketplace_accounts.id',ondelete='CASCADE'),index=True)
 inventory_id: Mapped[str]=mapped_column(String(100))
 total: Mapped[int|None]=mapped_column(Integer)
 available_quantity: Mapped[int|None]=mapped_column(Integer)
 not_available_quantity: Mapped[int|None]=mapped_column(Integer)
 not_available_detail: Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list)
 external_references: Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list)
 links: Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list)
 synced_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 sync_status: Mapped[str]=mapped_column(String(24),default='pending')
 sync_error: Mapped[str|None]=mapped_column(Text)
 operations_synced_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 operations_coverage_start: Mapped[date|None]=mapped_column(Date)
 operations_coverage_end: Mapped[date|None]=mapped_column(Date)
 operations_sync_status: Mapped[str]=mapped_column(String(24),default='pending',server_default='pending')
 operations_sync_error: Mapped[str|None]=mapped_column(Text)
class FullOperation(Base):
 __tablename__='ml_full_operations'
 __table_args__=(UniqueConstraint('account_id','operation_id',name='uq_full_operation_account_operation'),Index('ix_full_operation_account_date','account_id','date_created'),Index('ix_full_operation_inbound_inventory','inbound_id','inventory_id'))
 id: Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
 account_id: Mapped[str]=mapped_column(ForeignKey('marketplace_accounts.id',ondelete='CASCADE'),index=True)
 operation_id: Mapped[str]=mapped_column(String(100))
 inventory_id: Mapped[str|None]=mapped_column(String(100),index=True)
 inbound_id: Mapped[str|None]=mapped_column(String(100),index=True)
 date_created: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 operation_type: Mapped[str]=mapped_column(String(80))
 detail: Mapped[dict[str,Any]]=mapped_column(JSON,default=dict)
 result: Mapped[dict[str,Any]]=mapped_column(JSON,default=dict)
 external_references: Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list)
 payload: Mapped[dict[str,Any]]=mapped_column(JSON,default=dict)
 synced_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)
class FullShipment(TimestampMixin, Base):
 __tablename__='ml_full_shipments'
 __table_args__=(UniqueConstraint('account_id','inbound_id',name='uq_full_shipment_account_inbound'),Index('ix_full_shipment_account_updated','account_id','updated_at'))
 id: Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
 account_id: Mapped[str]=mapped_column(ForeignKey('marketplace_accounts.id',ondelete='CASCADE'),index=True)
 inbound_id: Mapped[str|None]=mapped_column(String(100))
 display_id: Mapped[str]=mapped_column(String(100),index=True)
 status: Mapped[str]=mapped_column(String(40),default='pending')
 delivery_mode: Mapped[str|None]=mapped_column(String(40))
 distribution_center: Mapped[str|None]=mapped_column(String(160))
 scheduled_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 expected_processing_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 physically_received_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
 panel_url: Mapped[str|None]=mapped_column(String(1000))
 notes: Mapped[str|None]=mapped_column(Text)
 created_by_id: Mapped[str|None]=mapped_column(ForeignKey('users.id'))
 items: Mapped[list['FullShipmentItem']]=relationship(cascade='all, delete-orphan',lazy='selectin')
 events: Mapped[list['FullShipmentEvent']]=relationship(cascade='all, delete-orphan',lazy='selectin',order_by='FullShipmentEvent.recorded_at')
class FullShipmentItem(Base):
 __tablename__='ml_full_shipment_items'
 __table_args__=(Index('ix_full_shipment_item_shipment_inventory','shipment_id','inventory_id'),)
 id: Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
 shipment_id: Mapped[str]=mapped_column(ForeignKey('ml_full_shipments.id',ondelete='CASCADE'),index=True)
 item_id: Mapped[str|None]=mapped_column(String(100))
 variation_id: Mapped[str|None]=mapped_column(String(100))
 inventory_id: Mapped[str|None]=mapped_column(String(100))
 sku: Mapped[str|None]=mapped_column(String(100),index=True)
 product_name: Mapped[str|None]=mapped_column(String(300))
 declared_quantity: Mapped[int|None]=mapped_column(Integer)
 physical_count: Mapped[int|None]=mapped_column(Integer)
 discrepancy_note: Mapped[str|None]=mapped_column(Text)
class FullShipmentEvent(Base):
 __tablename__='ml_full_shipment_events'
 __table_args__=(Index('ix_full_shipment_event_shipment_time','shipment_id','recorded_at'),)
 id: Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
 shipment_id: Mapped[str]=mapped_column(ForeignKey('ml_full_shipments.id',ondelete='CASCADE'),index=True)
 stage: Mapped[str]=mapped_column(String(50))
 source: Mapped[str]=mapped_column(String(20),default='manual')
 operational_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
 recorded_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)
 recorded_by_id: Mapped[str|None]=mapped_column(ForeignKey('users.id'))
 corrects_event_id: Mapped[str|None]=mapped_column(ForeignKey('ml_full_shipment_events.id'))
 note: Mapped[str|None]=mapped_column(Text)
