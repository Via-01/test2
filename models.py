# models.py
from sqlalchemy import Column, Integer, String, Boolean, Date, Enum, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import date
import enum

Base = declarative_base()

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class BloodType(enum.Enum):
    O_POSITIVE  = "O_POSITIVE"
    O_NEGATIVE  = "O_NEGATIVE"
    A_NEGATIVE  = "A_NEGATIVE"
    A_POSITIVE  = "A_POSITIVE"
    B_POSITIVE  = "B_POSITIVE"
    B_NEGATIVE  = "B_NEGATIVE"
    AB_POSITIVE = "AB_POSITIVE"
    AB_NEGATIVE = "AB_NEGATIVE"

class RequestStatus(enum.Enum):
    PENDING   = "PENDING"
    ACCEPTED  = "ACCEPTED"
    FULFILLED = "FULFILLED"
    VERIFIED  = "VERIFIED"
    REJECTED  = "REJECTED"

class DonationStatus(enum.Enum):
    COMPLETE          = "COMPLETE"
    SCREENING_FAILED  = "SCREENING_FAILED"

class LogAction(enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN  = "LOGIN"

# ---------------------------------------------------------------------------
# Address
# FIX: removed the erroneous inventory_fk — Address belongs to HospitalUnit,
#      not Inventory. The FK lives on HospitalUnit.addressId (correct already).
# ---------------------------------------------------------------------------

class Address(Base):
    __tablename__ = 'addresses'
    addressId = Column(String, primary_key=True)
    street    = Column(String)
    city      = Column(String)
    state     = Column(String)
    zipCode   = Column(String)
    latitude  = Column(Float)
    longitude = Column(Float)

    # Relationship back to HospitalUnit (the FK is on hospital_units.addressId)
    hospital_unit = relationship("HospitalUnit", back_populates="address", uselist=False)

class ContactInfo(Base):
    __tablename__ = 'contact_info'
    contactId = Column(String, primary_key=True)
    phone     = Column(String)
    email     = Column(String)
    user_fk   = Column(String, ForeignKey('users.userId'))

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    logId     = Column(String, primary_key=True)
    userId    = Column(String, ForeignKey('users.userId'))
    timestamp = Column(Date, default=date.today)
    type      = Column(Enum(LogAction))
    details   = Column(String)
    user      = relationship("User", back_populates="auditLogs")

class BloodComponent(Base):
    __tablename__ = 'blood_components'
    componentId       = Column(String, primary_key=True)
    name              = Column(String)
    storageConditions = Column(String)
    inventory_fk      = Column(String, ForeignKey('inventories.inventoryId'))
    inventory         = relationship("Inventory", back_populates="trackedComponents")

# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class Inventory(Base):
    __tablename__ = 'inventories'
    inventoryId    = Column(String, primary_key=True)
    unitsAvailable = Column(Integer)
    lastUpdated    = Column(Date)
    minOrderAmt    = Column(Integer)
    maxStorage     = Column(Float)
    blood_type     = Column(Enum(BloodType), nullable=False)
    component      = Column(String)
    unitId         = Column(String, ForeignKey('blood_bank_units.unitId'))

    trackedComponents = relationship("BloodComponent", back_populates="inventory")

# ---------------------------------------------------------------------------
# BloodBankUnit
# FIX: relationship was uselist=False (one-to-one) but a unit has MANY
#      inventory records. Changed to uselist=True (the default for one-to-many).
# ---------------------------------------------------------------------------

class BloodBankUnit(Base):
    __tablename__ = 'blood_bank_units'
    unitId        = Column(String, primary_key=True)
    name          = Column(String)
    contactNumber = Column(String)

    # One blood bank unit → many inventory rows
    inventories = relationship("Inventory", backref="blood_bank_unit")

class Donation(Base):
    __tablename__ = 'donations'
    donationId = Column(String, primary_key=True)
    donorId    = Column(String, ForeignKey('donors.userId'))
    date       = Column(Date)
    quantity   = Column(Integer)
    status     = Column(Enum(DonationStatus))
    blood_type = Column(Enum(BloodType))
    donor      = relationship("Donor", back_populates="donations")

class BloodRequest(Base):
    __tablename__ = 'blood_requests'
    requestId   = Column(String, primary_key=True)
    hospitalId  = Column(String, ForeignKey('hospital_units.unitId'))
    requestedId = Column(String)
    quantity    = Column(Integer)
    requestDate = Column(Date)
    isUrgent    = Column(Boolean, nullable=False, default=False)
    status      = Column(Enum(RequestStatus))
    blood_type  = Column(Enum(BloodType))

    hospital_unit = relationship("HospitalUnit", back_populates="bloodRequests")

class HospitalUnit(Base):
    __tablename__ = 'hospital_units'
    unitId        = Column(String, primary_key=True)
    name          = Column(String)
    contactNumber = Column(String)
    addressId     = Column(String, ForeignKey('addresses.addressId'))

    address       = relationship("Address", back_populates="hospital_unit", uselist=False)
    bloodRequests = relationship("BloodRequest", back_populates="hospital_unit")

# ---------------------------------------------------------------------------
# User hierarchy (joined-table inheritance)
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = 'users'
    userId       = Column(String, primary_key=True)
    username     = Column(String, unique=True)
    passwordHash = Column(String)
    timestamp    = Column(Date)
    user_type    = Column(String)

    __mapper_args__ = {
        'polymorphic_identity': 'user',
        'polymorphic_on':       user_type,
    }

    contactInfo             = relationship("ContactInfo", uselist=False, backref="user")
    auditLogs               = relationship("AuditLog", back_populates="user")
    sent_notifications      = relationship("Notification", foreign_keys="Notification.senderId",  back_populates="sender")
    received_notifications  = relationship("Notification", foreign_keys="Notification.receiverId", back_populates="receiver")
    reports                 = relationship("Report", back_populates="generator")

class Donor(User):
    __tablename__ = 'donors'
    userId           = Column(String, ForeignKey('users.userId'), primary_key=True)
    bloodType        = Column(Enum(BloodType), nullable=False)
    lastDonationDate = Column(Date, nullable=True)
    isEligible       = Column(Boolean, default=True)

    __mapper_args__ = {'polymorphic_identity': 'donor'}
    donations = relationship("Donation", back_populates="donor")

class HospitalAdmin(User):
    __tablename__ = 'hospital_admins'
    userId          = Column(String, ForeignKey('users.userId'), primary_key=True)
    hospitalInitId  = Column(String)

    __mapper_args__ = {'polymorphic_identity': 'hospital_admin'}

class BloodBankStaff(User):
    __tablename__ = 'blood_bank_staff'
    userId = Column(String, ForeignKey('users.userId'), primary_key=True)

    __mapper_args__ = {'polymorphic_identity': 'blood_bank_staff'}

# ---------------------------------------------------------------------------
# Auxiliary
# ---------------------------------------------------------------------------

class Notification(Base):
    __tablename__ = 'notifications'
    notificationId = Column(String, primary_key=True)
    senderId       = Column(String, ForeignKey('users.userId'))
    receiverId     = Column(String, ForeignKey('users.userId'))
    date           = Column(Date)
    type           = Column(String)
    content        = Column(String)
    isRead         = Column(Boolean, default=False)
    deliveryMethod = Column(String)

    sender   = relationship("User", foreign_keys=[senderId],   back_populates="sent_notifications")
    receiver = relationship("User", foreign_keys=[receiverId], back_populates="received_notifications")

class Report(Base):
    __tablename__ = 'reports'
    reportId    = Column(String, primary_key=True)
    generatorId = Column(String, ForeignKey('users.userId'))
    date        = Column(Date)
    type        = Column(String)
    content     = Column(String)

    generator = relationship("User", back_populates="reports")
