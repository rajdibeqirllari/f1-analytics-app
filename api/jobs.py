from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from time import time
from uuid import uuid4


class JobQueue:
    """Bounded local work queue. Render jobs use the existing VideoJobs worker."""
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='race-api')
        self.lock=Lock()
        self.items={}

    def submit(self,kind,task):
        with self.lock:
            if sum(j['status'] in ('queued','running') for j in self.items.values())>=6:
                raise ValueError('The work queue is full. Wait for an active task to finish.')
            key=uuid4().hex
            self.items[key]=dict(id=key,kind=kind,status='queued',progress=0,message='Waiting for a worker',
                                 error='',result=None,created=time(),cancel=Event())
        self.pool.submit(self._run,key,task)
        return key

    def _run(self,key,task):
        def progress(value,message='Working'):
            with self.lock:
                item=self.items[key]
                if item['cancel'].is_set():
                    raise InterruptedError('Task cancelled')
                item.update(progress=float(value),message=message,status='running')
        try:
            progress(.02,'Loading real session data')
            result=task(progress)
            progress(1,'Ready')
            with self.lock:
                self.items[key].update(status='complete',result=result)
        except InterruptedError:
            with self.lock:
                self.items[key].update(status='cancelled',message='Task cancelled')
        except Exception as exc:
            with self.lock:
                self.items[key].update(status='failed',error=str(exc),message='Task could not finish')

    def snapshot(self,key):
        with self.lock:
            item=self.items.get(key)
            return {k:v for k,v in item.items() if k!='cancel'} if item else None

    def cancel(self,key):
        with self.lock:
            item=self.items.get(key)
            if item:
                item['cancel'].set()

