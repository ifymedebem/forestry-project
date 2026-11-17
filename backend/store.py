"""PostgreSQL project store, with a zero-configuration SQLite development mode."""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Column, Float, Integer, String, Text, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATA = Path(os.getenv('DATA_DIR', 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DATA / "canopy.db"}')
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {})
Session = sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

def now():
    return datetime.now(timezone.utc).isoformat()

class Project(Base):
    __tablename__ = 'projects'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(String, default=now)
    status = Column(String, default='ready')
    stage = Column(String, default='Ready for analysis')
    boundary = Column(JSON)
    area_ha = Column(Float)
    document = Column(JSON)
    settings = Column(JSON)
    result = Column(JSON, default=dict)
    reviews = Column(JSON, default=dict)

class Job(Base):
    __tablename__ = 'jobs'
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    status = Column(String, default='queued', index=True)
    created_at = Column(String, default=now)
    started_at = Column(String)
    attempts = Column(Integer, default=0)
    error = Column(Text)
    result = Column(JSON)

def init_db():
    if engine.dialect.name == 'postgresql':
        with engine.begin() as conn:
            conn.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
    Base.metadata.create_all(engine)
    if engine.dialect.name == 'postgresql':
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE projects ADD COLUMN IF NOT EXISTS boundary_geom geometry(Geometry,4326)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS projects_boundary_idx ON projects USING GIST(boundary_geom)'))

def save_geometry(session, project):
    import json
    session.flush()
    if engine.dialect.name == 'postgresql':
        session.execute(text('UPDATE projects SET boundary_geom=ST_SetSRID(ST_GeomFromGeoJSON(:g),4326) WHERE id=:id'), {'g': json.dumps(project.boundary), 'id': project.id})

def s3():
    import boto3
    return boto3.client('s3', endpoint_url=os.getenv('S3_ENDPOINT_URL') or None, region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))

def put_file(key, data, content_type='application/octet-stream'):
    if os.getenv('S3_BUCKET'):
        s3().put_object(Bucket=os.environ['S3_BUCKET'], Key=key, Body=data, ContentType=content_type)
    else:
        path = DATA / 'files' / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {'key': key, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

def get_file(key):
    if os.getenv('S3_BUCKET'):
        return s3().get_object(Bucket=os.environ['S3_BUCKET'], Key=key)['Body'].read()
    return (DATA / 'files' / key).read_bytes()

