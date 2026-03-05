"""
Data models for the soul-legacy vault.
All sections follow the same pattern: structured Pydantic model + free-form notes.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date


class Asset(BaseModel):
    id: str
    name: str
    type: str                    # bank_account, brokerage, real_estate, vehicle, crypto, other
    institution: Optional[str]
    account_number: Optional[str] = None   # stored encrypted
    value_usd: Optional[float]
    beneficiary: Optional[str]
    notes: Optional[str]
    documents: List[str] = []    # filenames of attached docs


class Insurance(BaseModel):
    id: str
    type: str                    # life, health, property, auto, umbrella
    provider: str
    policy_number: Optional[str] = None
    coverage_usd: Optional[float]
    premium_monthly: Optional[float]
    beneficiary: Optional[str]
    expiry: Optional[date]
    notes: Optional[str]
    documents: List[str] = []


class LegalDoc(BaseModel):
    id: str
    type: str                    # will, trust, power_of_attorney, healthcare_directive
    date_signed: Optional[date]
    attorney: Optional[str]
    location: Optional[str]      # physical location of original
    notes: Optional[str]
    documents: List[str] = []


class Debt(BaseModel):
    id: str
    type: str                    # mortgage, auto_loan, student_loan, credit_card, other
    creditor: str
    account_number: Optional[str] = None
    balance_usd: Optional[float]
    monthly_payment: Optional[float]
    interest_rate: Optional[float]
    payoff_date: Optional[date]
    notes: Optional[str]


class Contact(BaseModel):
    id: str
    role: str                    # attorney, accountant, executor, trustee, doctor, financial_advisor
    name: str
    firm: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    notes: Optional[str]


class Beneficiary(BaseModel):
    id: str
    name: str
    relationship: str
    contact: Optional[str]
    share_pct: Optional[float]
    specific_assets: List[str] = []
    notes: Optional[str]


class DigitalAsset(BaseModel):
    id: str
    type: str                    # email, social_media, crypto_wallet, subscription, domain
    platform: str
    username: Optional[str] = None
    instructions: Optional[str]  # what to do with this account
    notes: Optional[str]


class Wish(BaseModel):
    id: str
    category: str                # funeral, medical, personal_property, message
    description: str
    recipient: Optional[str]
    notes: Optional[str]


class VaultMeta(BaseModel):
    owner_name: str
    owner_email: Optional[str]
    created_at: str
    updated_at: str
    version: str = "0.1.0"
    storage: str = "local"       # local | github | managed
    blockchain_anchored: bool = False
    last_checkin: Optional[str]  # for dead man's switch
