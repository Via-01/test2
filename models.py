# models.py (install sqlalchemy if you don't have it)
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date, Enum, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import date
import enum

# --- 1. Base Setup (In a real app, this is often in database.py) ---
# Define the base class for declarative class definitions
Base = declarative_base()

# --- 2. Enumerations (Matching the Diagram) ---

class BloodType(enum.Enum):
    O_POSITIVE = "O_POSITIVE"
    O_NEGATIVE = "O_NEGATIVE"
    A_NEGATIVE = "A_NEGATIVE"
    B_POSITIVE = "B_POSITIVE"
    B_NEGATIVE = "B_NEGATIVE"
    AB_POSITIVE = "AB_POSITIVE"
    AB_NEGATIVE = "AB_NEGATIVE"

class RequestStatus(enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    FULFILLED = "FULFILLED"

class DonationStatus(enum.Enum):
    COMPLETE = "COMPLETE"
    SCREENING_FAILED = "SCREENING_FAILED"

class LogAction(enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"

# --- 3. Core Entities and Auxiliary Classes ---

class Address(Base):
    __tablename__ = 'addresses'
    addressId = Column(String, primary_key=True)
    street = Column(String)
    city = Column(String)
    state = Column(String)
    zipCode = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    
    # Relationship with Inventory (1:1 - stores)
    inventory_fk = Column(String, ForeignKey('inventories.inventoryId'))
    
    # Relationship with HospitalUnit (1:1 - has)
    hospital_unit = relationship("HospitalUnit", back_populates="address", uselist=False)

class ContactInfo(Base):
    __tablename__ = 'contact_info'
    contactId = Column(String, primary_key=True)
    phone = Column(String)
    email = Column(String)
    # 1:1 relationship to User
    user_fk = Column(String, ForeignKey('users.userId'))

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    logId = Column(String, primary_key=True)
    userId = Column(String, ForeignKey('users.userId'))
    timestamp = Column(Date, default=date.today)
    type = Column(Enum(LogAction))
    details = Column(String)
    
    # Relationship to User (1:*)
    user = relationship("User", back_populates="auditLogs")

class BloodComponent(Base):
    __tablename__ = 'blood_components'
    componentId = Column(String, primary_key=True)
    name = Column(String) # e.g., Plasma, Platelets
    storageConditions = Column(String)
    
    # Relationship with Inventory (*:1 - tracks)
    inventory_fk = Column(String, ForeignKey('inventories.inventoryId'))
    inventory = relationship("Inventory", back_populates="trackedComponents")

class Inventory(Base):
    __tablename__ = 'inventories'
    inventoryId = Column(String, primary_key=True)
    unitsAvailable = Column(Integer)
    lastUpdated = Column(Date)
    minOrderAmt = Column(Integer)
    maxStorage = Column(Float) # Capacity
    
    # 1:1 relationship to Address (stores)
    address = relationship("Address", backref="inventory", uselist=False)
    
    # 1:1 relationship to BloodBankUnit (managed by)
    unitId = Column(String, ForeignKey('blood_bank_units.unitId'))
    
    # Relationship to BloodComponent (1:*) - tracks
    trackedComponents = relationship("BloodComponent", back_populates="inventory")

class BloodBankUnit(Base):
    __tablename__ = 'blood_bank_units'
    unitId = Column(String, primary_key=True)
    name = Column(String)
    contactNumber = Column(String)
    
    # 1:1 relationship to Inventory (manages)
    inventory = relationship("Inventory", backref="blood_bank_unit", uselist=False)

class Donation(Base):
    __tablename__ = 'donations'
    donationId = Column(String, primary_key=True)
    donorId = Column(String, ForeignKey('donors.userId')) # Link to Donor
    date = Column(Date)
    quantity = Column(Integer)
    status = Column(Enum(DonationStatus))
    
    # 1:1 relationship to BloodType (provides)
    blood_type = Column(Enum(BloodType))
    
    # Relationship to Donor (*:1)
    donor = relationship("Donor", back_populates="donations")

class BloodRequest(Base):
    __tablename__ = 'blood_requests'
    requestId = Column(String, primary_key=True)
    hospitalId = Column(String, ForeignKey('hospital_units.unitId')) # Link to HospitalUnit
    quantity = Column(Integer)
    date = Column(Date)
    emergency = Column(Boolean)
    status = Column(Enum(RequestStatus))
    
    # 1:1 relationship to BloodType (requires)
    blood_type = Column(Enum(BloodType))
    
    # Relationship to HospitalUnit (*:1)
    hospital_unit = relationship("HospitalUnit", back_populates="bloodRequests")

class HospitalUnit(Base):
    __tablename__ = 'hospital_units'
    unitId = Column(String, primary_key=True)
    name = Column(String)
    contactNumber = Column(String)
    
    # 1:1 relationship to Address (has)
    addressId = Column(String, ForeignKey('addresses.addressId'))
    address = relationship("Address", back_populates="hospital_unit", uselist=False)
    
    # 1:* relationship to BloodRequest (receives)
    bloodRequests = relationship("BloodRequest", back_populates="hospital_unit")

# --- 4. User and Inheritance Hierarchy ---

class User(Base):
    __tablename__ = 'users'
    userId = Column(String, primary_key=True)
    username = Column(String, unique=True)
    passwordHash = Column(String)
    timestamp = Column(Date)
    
    # Polymorphic type column for inheritance
    user_type = Column(String)
    __mapper_args__ = {
        'polymorphic_identity':'user',
        'polymorphic_on': user_type
    }
    
    # 1:1 relationship to ContactInfo
    contactInfo = relationship("ContactInfo", uselist=False, backref="user")
    
    # 1:* relationship to AuditLog
    auditLogs = relationship("AuditLog", back_populates="user")
    
    # 1:* relationship to Notification (sender/receiver)
    sent_notifications = relationship("Notification", foreign_keys="Notification.senderId", back_populates="sender")
    received_notifications = relationship("Notification", foreign_keys="Notification.receiverId", back_populates="receiver")
    
    # 1:* relationship to Report (generates)
    reports = relationship("Report", back_populates="generator")

class Donor(User):
    __tablename__ = 'donors'
    userId = Column(String, ForeignKey('users.userId'), primary_key=True)
    lastDonationDate = Column(Date, nullable=True)
    isEligible = Column(Boolean, default=True)
    # trackHealthMetrics is complex, might be another table or JSON field in advanced ORM
    
    __mapper_args__ = {
        'polymorphic_identity':'donor',
    }
    
    # 1:* relationship to Donation (offers)
    donations = relationship("Donation", back_populates="donor")

class HospitalAdmin(User):
    __tablename__ = 'hospital_admins'
    userId = Column(String, ForeignKey('users.userId'), primary_key=True)
    hospitalInitId = Column(String)
    
    __mapper_args__ = {
        'polymorphic_identity':'hospital_admin',
    }

class BloodBankStaff(User):
    __tablename__ = 'blood_bank_staff'
    userId = Column(String, ForeignKey('users.userId'), primary_key=True)
    
    __mapper_args__ = {
        'polymorphic_identity':'blood_bank_staff',
    }
    # 1:* relationship to BloodRequest (creates) - Implied, we'll model it here
    # created_requests = relationship("BloodRequest", backref="creator") # Requires a foreign key on BloodRequest

# --- 5. Auxiliary Service Classes (Notifications, Reports, Matching) ---

class Notification(Base):
    __tablename__ = 'notifications'
    notificationId = Column(String, primary_key=True)
    senderId = Column(String, ForeignKey('users.userId'))
    receiverId = Column(String, ForeignKey('users.userId'))
    date = Column(Date)
    type = Column(String)
    content = Column(String)
    isRead = Column(Boolean, default=False)
    deliveryMethod = Column(String) # e.g., SMS, FCM
    
    # Relationships to User
    sender = relationship("User", foreign_keys=[senderId], back_populates="sent_notifications")
    receiver = relationship("User", foreign_keys=[receiverId], back_populates="received_notifications")

class Report(Base):
    __tablename__ = 'reports'
    reportId = Column(String, primary_key=True)
    generatorId = Column(String, ForeignKey('users.userId')) # Link to User who generates it
    date = Column(Date)
    type = Column(String)
    content = Column(String)
    
    # Relationship to User (*:1)
    generator = relationship("User", back_populates="reports")

# MatchingService class represents business logic, not a database table.
# It would be implemented as a separate service class/module (e.g., services/matching_service.py).