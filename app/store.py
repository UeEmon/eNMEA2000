import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text, Float, select, func, or_

class WatchConflict(Exception):
    def __init__(self, records):
        self.records = records

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
        self.watch = Table('watch_vessels', meta,
            Column('id', Integer, primary_key=True), Column('mmsi', String(9), unique=True),
            Column('imo', String(7), unique=True), Column('name', String(120), nullable=False),
            Column('notes', String(500), nullable=False), Column('created_at', String(40), nullable=False),
            Column('updated_at', String(40), nullable=False), Column('last_alert_at', String(40)))
        self.identities = Table('ais_identities', meta, Column('mmsi', String(9), primary_key=True),
            Column('imo', String(7)), Column('shipname', String(120)))
        self.alerts = Table('watch_alerts', meta, Column('id', Integer, primary_key=True),
            Column('watch_id', Integer, nullable=False), Column('event_id', Integer, nullable=False),
            Column('received_at', String(40), nullable=False), Column('source', String(180)),
            Column('mmsi', String(9)), Column('imo', String(7)), Column('name', String(120)),
            Column('matched_by', String(12)))
        meta.create_all(self.engine)
        if url.startswith('sqlite'):
            with self.engine.connect() as c: c.exec_driver_sql('PRAGMA journal_mode=WAL')

    def add(self, rows):
        with self.engine.begin() as c:
            watched = [dict(r._mapping) for r in c.execute(select(self.watch))]
            mmsis={r.get('mmsi') for r in rows if r.get('mmsi')}
            known = {r.mmsi: dict(r._mapping) for r in c.execute(select(self.identities).where(self.identities.c.mmsi.in_(mmsis)))} if mmsis else {}
            now = datetime.now(timezone.utc)
            for row in rows:
                values = {k: row.get(k) for k in ['received_at','source','sentence_type','status','mmsi','latitude','longitude']}
                result = c.execute(self.events.insert().values(**values, payload=json.dumps(row, ensure_ascii=False)))
                row['id'] = result.inserted_primary_key[0]
                if row.get('status')!='ok' or row.get('sentence_type') not in ('VDM','VDO') or not row.get('mmsi'): continue
                mmsi=row['mmsi']; data=row.get('decoded') or {}
                previous=known.get(mmsi,{})
                imo=str(data.get('imo') or previous.get('imo') or '')
                msg_type=data.get('msg_type')
                if msg_type in (5,19,24):
                    shipname=str(data.get('shipname') or data.get('name') or '').strip(' @') or previous.get('shipname')
                    identity={'mmsi':mmsi,'imo':imo or None,'shipname':shipname or None}
                    c.execute(self.identities.delete().where(self.identities.c.mmsi==mmsi))
                    c.execute(self.identities.insert().values(**identity))
                    known[mmsi]=identity
                for target in watched:
                    by_mmsi=target['mmsi']==mmsi if target['mmsi'] else False
                    by_imo=target['imo']==imo if target['imo'] and imo else False
                    if not (by_mmsi or by_imo): continue
                    last=target['last_alert_at']
                    if last and now-datetime.fromisoformat(last)<timedelta(seconds=60): continue
                    stamp=now.isoformat();target['last_alert_at']=stamp
                    c.execute(self.watch.update().where(self.watch.c.id==target['id']).values(last_alert_at=stamp))
                    alert=dict(watch_id=target['id'],event_id=row['id'],received_at=row['received_at'],
                        source=row['source'],mmsi=mmsi,imo=imo or None,name=target['name'],
                        matched_by='MMSI' if by_mmsi else 'IMO')
                    alert['id']=c.execute(self.alerts.insert().values(**alert)).inserted_primary_key[0]
                    row.setdefault('watch_alerts',[]).append(alert)
        return rows

    def watchlist(self):
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(self.watch).order_by(self.watch.c.id.desc()))]

    def watch_save(self, item, watch_id=None):
        with self.engine.begin() as c:
            fields={'mmsi':item.get('mmsi') or None,'imo':item.get('imo') or None,
                    'name':item['name'],'notes':item.get('notes') or ''}
            checks=[self.watch.c[key]==value for key,value in fields.items() if key in ('mmsi','imo') and value]
            duplicates=[dict(r._mapping) for r in c.execute(select(self.watch).where(or_(*checks)))]
            duplicates=[r for r in duplicates if r['id']!=watch_id]
            if duplicates: raise WatchConflict(duplicates)
            stamp=datetime.now(timezone.utc).isoformat()
            if watch_id is None:
                result=c.execute(self.watch.insert().values(**fields,created_at=stamp,updated_at=stamp))
                watch_id=result.inserted_primary_key[0]
            else:
                result=c.execute(self.watch.update().where(self.watch.c.id==watch_id).values(**fields,updated_at=stamp,last_alert_at=None))
                if not result.rowcount: return None
            return dict(c.execute(select(self.watch).where(self.watch.c.id==watch_id)).one()._mapping)

    def watch_delete(self, watch_id):
        with self.engine.begin() as c:
            return bool(c.execute(self.watch.delete().where(self.watch.c.id==watch_id)).rowcount)

    def identity(self, mmsi):
        with self.engine.connect() as c:
            row=c.execute(select(self.identities).where(self.identities.c.mmsi==mmsi)).first()
            return dict(row._mapping) if row else None

    def recent_alerts(self, limit=100):
        with self.engine.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(self.alerts).order_by(self.alerts.c.id.desc()).limit(limit))]

    def latest_position(self, mmsi):
        query=select(self.events).where(self.events.c.mmsi==mmsi,self.events.c.status=='ok',
            self.events.c.latitude.is_not(None),self.events.c.longitude.is_not(None)).order_by(self.events.c.id.desc()).limit(1)
        with self.engine.connect() as c:
            row=c.execute(query).first()
            return dict(json.loads(row.payload),id=row.id) if row else None

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
            c.execute(self.alerts.delete())
            c.execute(self.identities.delete())
            c.execute(self.watch.update().values(last_alert_at=None))
        return {'events_deleted': events, 'jobs_deleted': jobs}
