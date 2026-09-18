"""Durable synthetic case processing. No provider calls or external side effects.

The caller authenticates a principal and constructs a tenant-scoped Workflow.
The database and approval methods are trusted application-side components.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid


STATES = ('requested', 'context_retrieved', 'proposed', 'validated',
          'awaiting_approval', 'approved', 'executed', 'completed', 'failed')


def _text(value, label, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label} must be a nonempty string of at most {limit} characters')
    return value


def _version(value):
    if type(value) is not int or value < 1:
        raise ValueError('memory version must be a positive integer')
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


class Workflow:
    """SQLite-backed single-host runner for trusted, synthetic case-note actions."""

    def __init__(self, database: str | Path, tenant: str, *, clock=time.time):
        self.database = str(database)
        self.tenant = _text(tenant, 'tenant', 100)
        self.clock = clock
        with self._transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS memory (
                  tenant TEXT, key TEXT, version INTEGER, value TEXT, source TEXT,
                  PRIMARY KEY(tenant, key, version));
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, tenant TEXT, request_key TEXT, request TEXT,
                  state TEXT, context TEXT, action TEXT, action_digest TEXT,
                  approval_digest TEXT, approval_expires REAL, attempts INTEGER DEFAULT 0,
                  error TEXT, deadline REAL, UNIQUE(tenant, request_key));
                CREATE TABLE IF NOT EXISTS effects (
                  job_id TEXT PRIMARY KEY, tenant TEXT, action_digest TEXT, action TEXT);
                CREATE TABLE IF NOT EXISTS audit (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, tenant TEXT,
                  event TEXT, state TEXT, timestamp REAL, latency_ms REAL, detail TEXT);
            ''')

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def put_memory(self, key, version, value, source):
        _text(key, 'memory key', 100)
        _version(version)
        _text(value, 'memory value')
        _text(source, 'source', 500)
        with self._transaction() as db:
            existing = db.execute('SELECT value, source FROM memory WHERE tenant=? AND key=? AND version=?',
                                  (self.tenant, key, version)).fetchone()
            if existing and tuple(existing) != (value, source):
                raise ValueError('conflicting content for immutable memory version')
            db.execute('INSERT OR IGNORE INTO memory VALUES (?, ?, ?, ?, ?)',
                       (self.tenant, key, version, value, source))

    def get_memory(self, key, version, *, tenant=None):
        if tenant is not None and tenant != self.tenant:
            raise PermissionError('cross-tenant memory access denied')
        with self._transaction() as db:
            return self._memory(db, key, version)

    def _memory(self, db, key, version):
        row = db.execute('SELECT key, version, value, source FROM memory WHERE tenant=? AND key=? AND version=?',
                         (self.tenant, key, version)).fetchone()
        if not row:
            raise ValueError('requested memory version is unavailable')
        return dict(row)

    def request(self, request_key, case_id, memory_key, memory_version, *,
                requires_approval=True, timeout=300, max_attempts=3):
        for label, value in [('request key', request_key), ('case id', case_id), ('memory key', memory_key)]:
            _text(value, label, 100)
        _version(memory_version)
        if type(requires_approval) is not bool:
            raise ValueError('requires_approval must be boolean')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
            raise ValueError('max_attempts must be between 1 and 10')
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 86400:
            raise ValueError('timeout must be finite, positive and at most 86400 seconds')
        request = {'schema_version': 1, 'case_id': case_id, 'memory_key': memory_key,
                   'memory_version': memory_version, 'requires_approval': requires_approval,
                   'timeout': timeout, 'max_attempts': max_attempts}
        job = str(uuid.uuid5(uuid.NAMESPACE_URL, _json([self.tenant, request_key])))
        start = time.perf_counter()
        with self._transaction() as db:
            row = db.execute('SELECT request FROM jobs WHERE id=? AND tenant=?', (job, self.tenant)).fetchone()
            if row:
                if row['request'] != _json(request):
                    raise ValueError('request key already belongs to different input')
                return job
            db.execute('INSERT INTO jobs (id,tenant,request_key,request,state,deadline) VALUES (?,?,?,?,?,?)',
                       (job, self.tenant, request_key, _json(request), 'requested', self.clock() + timeout))
            self._audit(db, job, 'request', 'requested', start)
        return job

    def _job(self, db, job):
        row = db.execute('SELECT * FROM jobs WHERE id=? AND tenant=?', (job, self.tenant)).fetchone()
        if row is None:
            raise PermissionError('job unavailable to this tenant')
        return row

    def _audit(self, db, job, event, state, start, detail=None):
        db.execute('INSERT INTO audit (job_id,tenant,event,state,timestamp,latency_ms,detail) VALUES (?,?,?,?,?,?,?)',
                   (job, self.tenant, event, state, self.clock(), (time.perf_counter()-start)*1000, _json(detail or {})))

    def approve(self, job, action_digest, *, expires_at):
        start = time.perf_counter()
        with self._transaction() as db:
            row = self._job(db, job)
            if row['state'] not in ('awaiting_approval', 'approved') or action_digest != row['action_digest']:
                raise PermissionError('approval must match this pending action digest')
            if type(expires_at) not in (int, float) or not math.isfinite(expires_at) or not self.clock() < expires_at <= row['deadline']:
                raise ValueError('approval expiry must be in the future and within job deadline')
            db.execute('UPDATE jobs SET state=?, approval_digest=?, approval_expires=? WHERE id=?',
                       ('approved', action_digest, expires_at, job))
            self._audit(db, job, 'approval', 'approved', start, {'action_digest': action_digest, 'expires_at': expires_at})

    def _validate_action(self, action, request, context):
        expected = {'kind', 'tenant', 'case_id', 'body', 'source', 'memory_version'}
        if not isinstance(action, dict) or set(action) != expected:
            raise ValueError('malformed action schema')
        if (action['kind'] != 'case_note' or action['tenant'] != self.tenant
                or action['case_id'] != request['case_id'] or action['source'] != context['source']
                or action['memory_version'] != context['version'] or type(action['memory_version']) is not int):
            raise ValueError('action disagrees with tenant, request or attributed context')
        _text(action['body'], 'action body')

    def advance(self, job, *, tool_output=None):
        start = time.perf_counter()
        with self._transaction() as db:
            row = self._job(db, job)
            state = row['state']
            request = json.loads(row['request'])
            if state in ('completed', 'failed'):
                pass
            elif state != 'executed' and self.clock() >= row['deadline']:
                db.execute("UPDATE jobs SET state='failed', error='deadline exceeded' WHERE id=?", (job,))
                self._audit(db, job, 'timeout', 'failed', start)
            else:
                try:
                    new_state = state
                    if state == 'requested':
                        context = self._memory(db, request['memory_key'], request['memory_version'])
                        db.execute('UPDATE jobs SET context=? WHERE id=?', (_json(context), job))
                        new_state = 'context_retrieved'
                    elif state == 'context_retrieved':
                        context = json.loads(row['context'])
                        action = tool_output if tool_output is not None else {
                            'kind': 'case_note', 'tenant': self.tenant, 'case_id': request['case_id'],
                            'body': f"Synthetic case note: {context['value']}",
                            'source': context['source'], 'memory_version': context['version']}
                        self._validate_action(action, request, context)
                        db.execute('UPDATE jobs SET action=?, action_digest=? WHERE id=?',
                                   (_json(action), _digest(action), job))
                        new_state = 'proposed'
                    elif state == 'proposed':
                        self._validate_action(json.loads(row['action']), request, json.loads(row['context']))
                        new_state = 'validated'
                    elif state == 'validated':
                        new_state = 'awaiting_approval' if request['requires_approval'] else 'approved'
                    elif state == 'approved':
                        if request['requires_approval'] and (row['approval_digest'] != row['action_digest']
                                or row['approval_expires'] is None or self.clock() >= row['approval_expires']):
                            new_state = 'awaiting_approval'
                        else:
                            action = json.loads(row['action'])
                            self._validate_action(action, request, json.loads(row['context']))
                            if _digest(action) != row['action_digest']:
                                raise ValueError('action changed after proposal')
                            # The synthetic effect and state transition commit together. No external API is invoked.
                            db.execute('INSERT OR IGNORE INTO effects VALUES (?, ?, ?, ?)',
                                       (job, self.tenant, row['action_digest'], row['action']))
                            new_state = 'executed'
                    elif state == 'executed':
                        new_state = 'completed'
                    if new_state != state:
                        db.execute('UPDATE jobs SET state=?, attempts=0, error=NULL WHERE id=?', (new_state, job))
                        self._audit(db, job, 'transition', new_state, start, {'from': state, 'action_digest': row['action_digest']})
                except (ValueError, TypeError, KeyError) as error:
                    attempts = row['attempts'] + 1
                    new_state = 'failed' if attempts >= request['max_attempts'] else state
                    db.execute('UPDATE jobs SET state=?, attempts=?, error=? WHERE id=?',
                               (new_state, attempts, str(error), job))
                    self._audit(db, job, 'attempt_failed', new_state, start, {'attempt': attempts, 'error': str(error)})
        return self.report(job)

    def report(self, job):
        with self._transaction() as db:
            row = self._job(db, job)
            trace = [dict(item) for item in db.execute(
                'SELECT sequence,event,state,timestamp,latency_ms,detail FROM audit WHERE job_id=? AND tenant=? ORDER BY sequence',
                (job, self.tenant))]
            for item in trace:
                item['detail'] = json.loads(item['detail'])
            effects = [dict(item) for item in db.execute(
                'SELECT action_digest,action FROM effects WHERE job_id=? AND tenant=?', (job, self.tenant))]
            for item in effects:
                item['action'] = json.loads(item['action'])
            return {'schema_version': 1, 'classification': 'synthetic', 'job_id': job, 'tenant': self.tenant,
                    'state': row['state'], 'attempts': row['attempts'], 'error': row['error'],
                    'action': json.loads(row['action']) if row['action'] else None,
                    'action_digest': row['action_digest'], 'effects': effects, 'trace': trace,
                    'token_usage': None, 'cost': None, 'provider_integration': 'not implemented'}


def compare_traces(left, right):
    def transitions(report):
        return [row['state'] for row in report['trace'] if row['event'] == 'transition']
    return {'same_transitions': transitions(left) == transitions(right),
            'left_states': transitions(left), 'right_states': transitions(right),
            'left_latency_ms': sum(row['latency_ms'] for row in left['trace']),
            'right_latency_ms': sum(row['latency_ms'] for row in right['trace']),
            'token_delta': None, 'cost_delta': None}
