import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import models

# Use a test SQLite database to verify structures
TEST_DATABASE_URL = "sqlite:///./test_orchestrator.db"

@pytest.fixture(scope="module")
def db_session():
    """
    Creates an in-memory SQLite database session for unit testing DB schemas.
    """
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        if os.path.exists("./test_orchestrator.db"):
            os.remove("./test_orchestrator.db")

def test_create_settings(db_session):
    """
    Verify that global settings record is correctly initialized.
    """
    settings = models.Settings(
        borg_ssh_port=12345,
        borg_repo_path="/data/borg",
        keep_daily=7,
        keep_weekly=4,
        keep_monthly=6,
        global_exclusions="/dev/*"
    )
    db_session.add(settings)
    db_session.commit()

    retrieved = db_session.query(models.Settings).first()
    assert retrieved is not None
    assert retrieved.borg_ssh_port == 12345
    assert retrieved.keep_daily == 7

def test_create_node_with_uuid(db_session):
    """
    Verify that nodes with EFI partition UUID can be saved and retrieved.
    """
    node = models.Node(
        hostname="test-edge-01",
        ip_address="192.168.1.50",
        ssh_port=22,
        status="NEEDS_BOOTSTRAP",
        disk_type="SATA",
        efi_uuid="4F2E-3A5B"
    )
    db_session.add(node)
    db_session.commit()

    retrieved = db_session.query(models.Node).filter(models.Node.hostname == "test-edge-01").first()
    assert retrieved is not None
    assert retrieved.ip_address == "192.168.1.50"
    assert retrieved.efi_uuid == "4F2E-3A5B"

def test_parse_ip_input():
    """
    Test parsing lists, ranges, and CIDR blocks into single IP strings.
    """
    from main import parse_ip_input

    # Test single
    assert parse_ip_input("192.168.1.100") == ["192.168.1.100"]

    # Test comma-separated list
    assert parse_ip_input("192.168.1.100, 192.168.1.101") == ["192.168.1.100", "192.168.1.101"]

    # Test range (short)
    assert parse_ip_input("192.168.1.50-52") == ["192.168.1.50", "192.168.1.51", "192.168.1.52"]

    # Test range (long)
    assert parse_ip_input("10.0.0.1-10.0.0.3") == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    # Test CIDR
    assert parse_ip_input("192.168.1.0/30") == ["192.168.1.1", "192.168.1.2"]

