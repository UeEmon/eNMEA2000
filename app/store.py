import json
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text, Float, select, func

class Store:
    def __init__(self, url):
        self.engine = create_engine(url, pool_pre_ping=True,
            connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {})
        meta = MetaData()
        self.events = Table('events', meta,
            Column('id', Integer, primary_key=True), Column('received_at', String(40), index=True),
            Column('source', String(180), index=True), Column('sentence_type', String(24), index=True),
            Column('status', String(24), index=True), Column('mmsi', String(16), index=True),
            Column('latitude', Float), Column('longitude', Float), Column('payload', Text))
        self.jobs = Table('jobs', meta, Column('id', String(40), primary_key=True), Column('payload', Text))
        meta.create_all(self.engine)
        if url.startswith('sqlite'):
            with self.engine.connect() as c: c.exec_driver_sql('PRAGMA journal_mode=WAL')

    def add(self, rows):
        with self.engine.begin() as c:
            for row in rows:
                values = {k: row.get(k) for k in ['received_at','source','sentence_type','status','mmsi','latitude','longitude']}
                result = c.execute(self.events.insert().values(**values, payload=json.dumps(row, ensure_ascii=False)))
                row['id'] = result.inserted_primary_key[0]
        return rows

    def recent(self, limit=200, before=None, source=None, kind=None, mmsi=None, after=None):
        query = select(self.events)
        for col, value in [('source',source),('sentence_type',kind),('mmsi',mmsi)]:
            if value: query = query.where(self.events.c[col] == value)
        if before: query = query.where(self.events.c.id < before)
        if after is not None: query = query.where(self.events.c.id > after)
        query = query.order_by(self.events.c.id.asc() if after is not None else self.events.c.id.desc()).limit(limit)
        with self.engine.connect() as c:
            return [dict(json.loads(r.payload), id=r.id) for r in c.execute(query)]

    def stats(self):
        with self.engine.connect() as c:
            statuses = dict(c.execute(select(self.events.c.status, func.count()).group_by(self.events.c.status)).all())
            kinds = dict(c.execute(select(self.events.c.sentence_type, func.count()).group_by(self.events.c.sentence_type)).all())
        return {'total': sum(statuses.values()), 'statuses': statuses, 'types': kinds}

    def save_job(self, job):
        with self.engine.begin() as c:
            c.execute(self.jobs.delete().where(self.jobs.c.id == job['id']))
            c.execute(self.jobs.insert().values(id=job['id'], payload=json.dumps(job, ensure_ascii=False)))

    def load_jobs(self):
        with self.engine.connect() as c: return [json.loads(r.payload) for r in c.execute(select(self.jobs))]

    def clear(self):
        """Remove stored events and import job metadata in one transaction; retain schema."""
        with self.engine.begin() as c:
            events = c.execute(self.events.delete()).rowcount
            jobs = c.execute(self.jobs.delete()).rowcount
        return {'events_deleted': events, 'jobs_deleted': jobs}
