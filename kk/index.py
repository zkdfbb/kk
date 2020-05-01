#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Author: zhangkai
Last modified: 2020-03-27 21:40:13
'''
import os  # NOQA: E402
import sys  # NOQA: E402
sys.path.append(os.path.dirname(os.path.abspath(__file__)))  # NOQA: E402

import datetime
import hashlib
import logging
import psutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from handler import bp as bp_disk
from tornado.options import define
from tornado.options import options
from tornado_utils import Application
from tornado_utils import bp_user
from utils import connect
from utils import AioEmail
from utils import Dict
from utils import Motor
from utils import AioRedis
from utils import Request

define('root', default='.', type=str)
define('git', default=None, type=str)
define('auth', default=False, type=bool)
define('tools', default=False, type=bool)
define('db', default='kk', type=str)


class Application(Application):

    def initialize(self):
        logging.getLogger('apscheduler').setLevel(logging.ERROR)
        self.root = Path(options.root).expanduser().absolute()
        self.http = Request(lib='tornado')
        self.cache = {}
        self.sched = BackgroundScheduler()
        self.sched.add_job(self.scan, 'cron', minute='0', hour='*')
        self.sched.add_job(self.scan, 'date', run_date=datetime.datetime.now() + datetime.timedelta(seconds=1))
        self.sched.start()
        if options.auth or options.tools:
            self.db = Motor(options.db)
        if options.auth:
            self.email = AioEmail()
            self.rd = AioRedis()

    def get_md5(self, path):
        if path.is_file() and options.auth:
            md5 = hashlib.md5()
            with path.open('rb') as fp:
                while True:
                    data = fp.read(4194304)
                    if not data:
                        break
                    md5.update(data)
            return md5.hexdigest()

    def scan_dir(self, root):
        if not root.exists():
            return []
        st_mtime = root.stat().st_mtime
        if root in self.cache and st_mtime == self.cache[root][0]:
            entries = self.cache[root][1]
        else:
            entries = []
            for item in root.iterdir():
                if not item.exists():
                    continue
                if item.name.startswith('.'):
                    continue
                path = item.relative_to(self.root)
                entries.append(Dict({
                    'path': path,
                    'mtime': int(item.stat().st_mtime),
                    'size': item.stat().st_size,
                    'md5': self.get_md5(item),
                    'is_dir': item.is_dir(),
                }))
            entries.sort(key=lambda x: str(x.path).lower())
            self.cache[root] = [st_mtime, entries]

        return entries

    def scan(self):
        dirs = [self.root] + [f for f in self.root.rglob('*') if f.is_dir()]
        self.logger.info(f'scan {self.root}: {len(dirs)} dirs')
        with ThreadPoolExecutor(min(20, len(dirs))) as executor:
            executor.map(self.scan_dir, dirs)
        count = sum([len(v[1]) for v in self.cache.values()])
        self.logger.info(f'scan {self.root}: {count} files and dirs')

    def get_port(self):
        port = 8000
        try:
            connections = psutil.net_connections()
            ports = set([x.laddr.port for x in connections])
            while port in ports:
                port += 1
        except:
            while connect('127.0.0.1', port):
                port += 1
        return port


def main():
    kwargs = dict(
        static_path=Path(__file__).parent.absolute() / 'static',
        template_path=Path(__file__).parent.absolute() / 'templates'
    )
    app = Application(**kwargs)
    app.register(bp_disk, bp_user)
    port = options.port if options.auth or options.port != 8000 else app.get_port()
    app.run(port=port, max_buffer_size=128 * 1024 * 1024)


if __name__ == '__main__':
    main()
