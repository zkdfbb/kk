#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Author: zhangkai
Last modified: 2020-03-27 21:17:57
'''
import asyncio
import datetime
import functools
import hashlib
import io
import json
import math
import os
import re
import shutil
import string
import tarfile
import tempfile
import time
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import markdown
import tornado.web
import yaml
from bson import ObjectId
from tornado.concurrent import run_on_executor
from tornado_utils import BaseHandler
from tornado_utils import Blueprint
from utils import Dict

bp = Blueprint(__name__)


def check_auth(method):
    @functools.wraps(method)
    async def wrapper(self, name, *args, **kwargs):
        if await self.check(name):
            await method(self, name, *args, **kwargs)
        elif self.request.method in ['GET', 'HEAD']:
            self.redirect(self.get_login_url())
        else:
            self.finish({'err': 1, 'msg': '无权限'})

    return wrapper


class BaseHandler(BaseHandler):

    executor = ThreadPoolExecutor(10)

    default = {
        'ppt.png': ['.ppt', '.pptx'],
        'word.png': ['.doc', '.docx'],
        'excel.png': ['.xls', '.xlsx'],
        'pdf.png': ['.pdf'],
        'txt.png': ['.txt'],
        'vue.png': ['.vue'],
        'exe.png': ['.exe'],
        'mac.png': ['.dmg', '.pkg'],
        'apk.png': ['.apk'],
        'iso.png': ['.iso'],
        'json.png': ['.json', '.yml', '.yaml'],
        'ini.png': ['.ini'],
        'markdown.png': ['.md'],
        'kindle.png': ['.mobi', '.epub'],
        'database.png': ['.db', '.sql'],
        'image.png': ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.svg', '.ai'],
        'audio.png': ['.amr', '.ogg', '.wav', '.mp3', '.flac', '.ape'],
        'video.png': ['.rmvb', '.rm', '.mkv', '.mp4', '.avi', '.wmv', '.flv', '.m3u8', '.ts'],
        'zip.png': ['.rar', '.tar', '.tgz', '.gz', '.bz2', '.xz', '.zip', '.7z', '.z'],
        'c.png': ['.c', '.h'],
        'cpp.png': ['.cpp'],
        'csharp.png': ['.cs'],
        'python.png': ['.py', '.pyc'],
        'bash.png': ['.sh'],
        'go.png': ['.go'],
        'java.png': ['.java', '.javac', '.class', '.jar'],
        'javascript.png': ['.js'],
        'html.png': ['.html'],
        'css.png': ['.css', '.less', '.sass', '.scss'],
    }
    icon = {}
    for key, value in default.items():
        for v in value:
            icon[v] = key

    @staticmethod
    def convert_size(size):
        if size / (1024 * 1024 * 1024.0) >= 1:
            return '%.1f GB' % (size / (1024 * 1024 * 1024.0))
        elif size / (1024 * 1024.0) >= 1:
            return '%.1f MB' % (size / (1024 * 1024.0))
        else:
            return '%.1f KB' % (size / 1024.0)

    @staticmethod
    def convert_time(mtime):
        if isinstance(mtime, (int, float)):
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        elif isinstance(mtime, datetime.datetime):
            return mtime.strftime("%Y-%m-%d %H:%M:%S")
        else:
            return mtime

    @run_on_executor
    def get_md5(self, path):
        return self.app.get_md5(path)


@bp.route('/')
class IndexHandler(BaseHandler):

    def get(self):
        if self.app.options.auth:
            if self.current_user:
                self.redirect(f'/disk/{self.current_user.id}')
            else:
                self.redirect('/disk/public')
        else:
            self.redirect('/disk')


@bp.route('/admin')
class AdminHandler(BaseHandler):

    @tornado.web.authenticated
    async def get(self):
        self.render('admin.html')

    @tornado.web.authenticated
    async def post(self):
        if self.args.kindle and self.args.kindle != self.current_user.kindle:
            code = await self.rd.get(f'{self.prefix}_code_{self.args.kindle}')
            if self.args.kindle and not (code and code == self.args.code):
                return self.finish({'err': 1, 'msg': '邮箱验证码不正确'})

        update = {
            'public': self.args.public == 'on'
        }
        if self.args.kindle:
            update['kindle'] = self.args.kindle
        await self.db.users.update_one({'_id': self.current_user._id}, {'$set': update})
        self.finish({'err': 0})


@bp.route('/manage')
class ManageHandler(BaseHandler):

    @tornado.web.authenticated
    async def get(self):
        if not self.current_user.admin:
            raise tornado.web.HTTPError(403)

        query = self.get_args()
        if query.username:
            query.username = {'username': {'$regex': re.compile(query.username)}}
        entries = await self.query('users', query, schema={'id': int})
        self.render('manage.html', entries=entries)

    @tornado.web.authenticated
    async def post(self):
        if not self.current_user.admin:
            return self.finish({'err': 1, 'msg': '当前用户无权限'})

        _id = self.get_argument('id', None)
        if not _id:
            return self.finish({'err': 1, 'msg': '用户未指定'})
        user = await self.db.users.find_one({'_id': ObjectId(_id)})
        if not user:
            return self.finish({'err': 1, 'msg': '用户不存在'})
        if user._id == self.current_user._id:
            return self.finish({'err': 1, 'msg': '不允许自杀'})

        if self.args.action == 'delete':
            await self.db.users.delete_one({'_id': user._id})
        elif self.args.action == 'deny':
            await self.db.users.update_one({'_id': user._id}, {'$set': {'deny': True}})
        elif self.args.action == 'toggle':
            if user.admin:
                await self.db.users.update_one({'_id': user._id}, {'$unset': {'admin': 1}})
            else:
                await self.db.users.update_one({'_id': user._id}, {'$set': {'admin': True}})

        self.finish({'err': 0})


@bp.route('/share')
class ShareHandler(BaseHandler):

    async def get(self):
        if self.app.options.auth:
            if self.current_user:
                token = self.args.token if self.current_user.admin and self.args.token else self.current_user.token
                docs = await self.query('share', {'token': token})
                entries = []
                for doc in docs:
                    if doc.expired_at and doc.expired_at < datetime.datetime.now():
                        await self.db.share.delete_one({'_id': doc._id})
                    else:
                        entries.append(Dict({
                            'path': Path(doc.name),
                            'mtime': doc.mtime,
                            'size': doc.size,
                            'is_dir': doc.is_dir,
                            'md5': doc.md5,
                            'key': doc._id,
                            'expired_at': doc.expired_at,
                            'shared': True,
                        }))
                self.render('index.html', entries=entries, absolute=True)
            else:
                self.redirect(self.get_login_url())
        else:
            self.redirect('/disk')


@bp.route('/disk/?(.*)')
@bp.route('/file/?(.*)')
class DiskHandler(tornado.web.StaticFileHandler, BaseHandler):

    def __init__(self, application, request, **kwargs):
        tornado.web.StaticFileHandler.__init__(self, application, request, path=self.app.root)
        BaseHandler.__init__(self, application, request, path=self.app.root)

    def compute_etag(self):
        if hasattr(self, 'absolute_path'):
            return super().compute_etag()

    @run_on_executor
    def search(self, name):
        entries = []
        q = self.args.q.lower()
        for key, files in self.app.cache.items():
            for doc in files[1]:
                if doc.path.name.lower().find(q) >= 0:
                    if self.app.options.auth and not str(doc.path).startswith(name):
                        continue
                    entries.append(doc)
        doc = self.get_args(page=1, count=50)
        self.args.total = len(entries)
        self.args.pages = int(math.ceil(len(entries) / doc.count))
        entries = entries[(doc.page - 1) * doc.count:doc.page * doc.count]
        return entries

    @run_on_executor
    def listdir(self, root):
        entries = self.app.scan_dir(root)
        doc = self.get_args(page=1, count=50, order=- 1)
        if self.args.sort == 'time':
            entries.sort(key=lambda x: x.mtime, reverse=(self.args.order == - 1))
        elif self.args.sort == 'size':
            entries.sort(key=lambda x: x.size, reverse=(self.args.order == - 1))
        else:
            entries.sort(key=lambda x: x.path, reverse=(self.args.order == - 1))
        self.args.total = len(entries)
        self.args.pages = int(math.ceil(len(entries) / doc.count))
        entries = entries[(doc.page - 1) * doc.count:doc.page * doc.count]
        return entries

    @run_on_executor
    def download(self, root):
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        filename = urllib.parse.quote(root.name)
        stream = io.BytesIO()
        zf = zipfile.ZipFile(stream, 'a', zipfile.ZIP_DEFLATED, False)
        for f in root.rglob('*'):
            if f.is_file():
                zf.writestr(str(f.relative_to(root)), f.read_bytes())
        #  Mark the files as having been created on Windows so that Unix permissions are not inferred as 0000
        for zfile in zf.filelist:
            zfile.create_system = 0
        zf.close()
        data = stream.getvalue()
        stream.close()
        self.set_header('Content-Disposition', f'attachment;filename={filename}.zip')
        self.finish(data)

    def get_nodes(self, root):
        nodes = []
        key = self.app.root / root
        if key in self.app.cache:
            entries = self.app.cache[key][1]
            for doc in entries:
                if doc.is_dir:
                    nodes.append({'title': doc.path.name, 'href': f'/disk/{doc.path}', 'children': self.get_nodes(doc.path)})
                else:
                    nodes.append({'title': doc.path.name, 'href': f'/disk/{doc.path}'})
        return nodes

    async def get_info(self, name):
        info = Dict()
        if self.app.options.auth and not name.startswith('public'):
            doc = await self.db.share.find_one({'name': name, 'token': self.current_user.token})
            info.share = True if doc else False
        if self.app.options.git and self.current_user.admin:
            doc = await self.db.files.find_one({'name': name})
            info.git = True if doc else False
        return info

    def set_default_headers(self):
        self.set_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.set_header('Pragma', 'no-cache')
        self.set_header('Expires', '0')

    def set_extra_headers(self, path):
        if path.endswith('.ts'):
            self.set_header('Content-Type', 'application/octet-stream')

    def preview_html(self, html, padding=0, background='#23241f'):
        lines = [
            '<html><head>',
            '<link rel="stylesheet" href="/static/src/css/monokai_sublime.css">',
            f'</head><body style="padding:{padding}px;margin:0;background:{background};">',
            html,
            '<script src="/static/src/js/highlight.pack.min.js"></script>',
            '<script>hljs.initHighlightingOnLoad()</script>',
            '</body></html>'
        ]
        self.finish(''.join(lines))

    def preview_office(self):
        url = f'http://{self.request.host}{self.request.path}'
        if self.app.options.auth:
            if self.current_user.token:
                url += f'?token={self.current_user.token}'
            elif self.args.key:
                url += f'?key={self.args.key}'
        src = urllib.parse.quote(url, safe=string.printable)
        url = f'https://view.officeapps.live.com/op/view.aspx?src={src}'
        self.redirect(url)

    def preview_video(self):
        url = self.request.path
        if self.app.options.auth:
            url += '?token=' + (self.args.key or self.current_user.token)
        html = [
            '<html><head>',
            '<link rel="stylesheet" href="/static/src/css/DPlayer.min.css">',
            '</head><body>',
            '<div id="video"></div>',
            '<script src="/static/src/js/flv.min.js"></script>',
            '<script src="/static/src/js/hls.min.js"></script>',
            '<script src="/static/src/js/DPlayer.min.js"></script>',
            '<script>new DPlayer({container: document.getElementById("video"), autoplay: true, video: { type: "auto", url: "' + url + '" } })</script>',
            '</body></html>'
        ]
        self.finish(''.join(html))

    def preview_zip(self, path):
        zf = zipfile.ZipFile(path)
        items = zf.infolist()
        entries = []
        for item in items:
            try:
                item.filename = item.filename.encode('cp437').decode('gbk')
            except:
                pass
            entries.append(Dict({
                'path': Path(item.filename),
                'mtime': datetime.datetime(*item.date_time).strftime("%Y-%m-%d %H:%M:%S"),
                'size': item.file_size,
                'is_dir': item.is_dir(),
            }))
        self.render('index.html', entries=entries, absolute=True)

    def preview_tar(self, path):
        tf = tarfile.open(path)
        items = tf.getmembers()
        entries = []
        for item in items:
            entries.append(Dict({
                'path': Path(item.name),
                'mtime': item.mtime,
                'size': item.size,
                'is_dir': item.isdir(),
            }))
        self.render('index.html', entries=entries, absolute=True)

    async def check(self, name):
        if not self.app.options.auth or self.current_user.admin:
            return True
        key = name.split('/')[0]
        if key == str(self.current_user.id):
            return True
        if self.request.method not in ['GET', 'HEAD']:
            return False
        if key == 'public':
            return True
        if not key.isdigit():
            return False
        user = await self.db.users.find_one({'id': int(key)})
        if user and user.public:
            return True
        if not self.args.key:
            return False
        doc = await self.db.share.find_one({'_id': ObjectId(self.args.key)})
        if not doc:
            return False
        if doc.expired_at and doc.expired_at < datetime.datetime.now():
            return await self.db.share.delete_one({'_id': doc._id})
        return name.startswith(doc.name)

    async def send(self, name, include_body=True):
        if self.app.options.git and include_body:
            doc = await self.db.files.find_one({'name': name})
            if doc:
                return self.redirect(doc.url)
        await super().get(name, include_body)

    @check_auth
    async def get(self, name, include_body=True):
        path = self.root / name
        if self.args.q:
            entries = await self.search(name)
            self.render('index.html', entries=entries, absolute=True)
        elif self.args.f == 'tree':
            nodes = self.get_nodes(path)
            self.finish({'nodes': nodes})
        elif self.args.f == 'info':
            info = await self.get_info(name)
            self.finish(info)
        elif self.args.f == 'download':
            self.set_header('Content-Type', 'application/octet-stream')
            zh = re.compile('[\u4e00-\u9fa5]+')
            if zh.search(path.name):
                filename = urllib.parse.quote(path.name.encode('UTF-8'))
            else:
                filename = urllib.parse.quote(path.name)
            if path.is_file():
                self.set_header('Content-Disposition', f'attachment;filename={filename}')
                await self.send(name, include_body)
            else:
                await self.download(path)
        elif path.is_file() and self.args.f == 'preview':
            if path.suffix.lower() == '.zip':
                self.preview_zip(path)
            elif re.match('.(tar|gz|bz2|tgz|z)$', path.suffix.lower()) and tarfile.is_tarfile(path):
                self.preview_tar(path)
            elif re.match('.(docx|doc|xlsx|xls|pptx|ppt)$', path.suffix.lower()):
                self.preview_office()
            elif re.match('.(mp4|flv|m3u8)$', path.suffix.lower()):
                self.preview_video()
            elif re.match('.(yaml|yml)$', path.suffix.lower()):
                self.finish(yaml.load(open(path)))
            elif path.suffix.lower() == '.md':
                exts = ['markdown.extensions.extra', 'markdown.extensions.codehilite', 'markdown.extensions.tables', 'markdown.extensions.toc']
                html = markdown.markdown(path.read_text(), extensions=exts)
                self.preview_html(html, padding=20, background='#fff')
            elif path.suffix.lower() == '.ipynb':
                with tempfile.NamedTemporaryFile('w+', suffix=f'.html', delete=True) as fp:
                    command = f'jupyter nbconvert --to html --template full --output {fp.name} {path}'
                    dl = await asyncio.create_subprocess_shell(command)
                    await dl.wait()
                    self.finish(fp.read().replace('<link rel="stylesheet" href="custom.css">', ''))
            elif re.match('.(py|sh|h|c|cpp|js|css|html|java|go|ini|vue)$', path.suffix.lower()):
                code = {
                    '.py': 'python',
                    '.sh': 'bash',
                    '.h': 'c',
                    '.js': 'javascript',
                    '.vue': 'javascript',
                }.get(path.suffix.lower(), path.suffix.lower()[1:])
                try:
                    text = path.read_text()
                except:
                    text = path.read_text(encoding='unicode_escape')
                self.preview_html(f'<pre><code class="{code}">{ tornado.escape.xhtml_escape(text) }</code></pre>')
            else:
                await self.send(name, include_body)
        elif path.is_file():
            await self.send(name, include_body)
        else:
            entries = await self.listdir(path)
            self.render('index.html', entries=entries, absolute=False)

    async def merge(self, path):
        dirname = Path(f'/tmp/{self.args.guid}')
        filename = path / urllib.parse.unquote(self.args.name)
        filename.parent.mkdir(parents=True, exist_ok=True)
        chunks = int(list(dirname.glob("*"))[0].name.split('_')[0])
        md5 = hashlib.md5()
        with filename.open('wb') as fp:
            for i in range(int(chunks)):
                chunk = dirname / f'{chunks}_{i}'
                if not chunk.exists():
                    return self.finish({'err': 1, 'msg': f'missing chunk {i}'})
                data = chunk.read_bytes()
                md5.update(data)
                fp.write(data)
        md5 = md5.hexdigest()
        if self.args.md5 and self.args.md5 != 'undefined' and self.args.md5 != md5:
            self.finish({'err': 1, 'msg': f'check md5 failed'})
        else:
            shutil.rmtree(dirname)
            self.finish({'err': 0})

    async def upload(self, path):
        if self.args.action == 'merge':
            await self.merge(path)
        elif self.args.chunks and self.args.chunk:
            filename = Path(f'/tmp/{self.args.guid}/{self.args.chunks}_{self.args.chunk}')
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_bytes(self.request.files['file'][0].body)
            self.finish({'err': 0})
        else:
            path.mkdir(parents=True, exist_ok=True)
            for items in self.request.files.values():
                for item in items:
                    filename = path / urllib.parse.unquote(item.filename)
                    filename.parent.mkdir(parents=True, exist_ok=True)
                    filename.write_bytes(item.body)
            self.finish({'err': 0})

    async def git_add(self, name):
        if not self.current_user.admin or not self.app.options.auth or not self.app.options.git:
            return False

        doc = await self.db.git.find_one({'name': name})
        if doc:
            self.logger.info(f'{name} is already in git')
            return True

        path = self.root / name
        names = [name]
        if path.is_symlink():
            names.append(path.resolve().relative_to(self.root))
        for name in names:
            command = f"cd '{self.root}' && git add '{name}' && git commit -m 'add {name}' && git push origin master"
            self.logger.info(command)
            p = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            output, _ = await p.communicate()
            if p.returncode == 0:
                self.logger.info(f'git add {name} succeed')
                doc = {
                    'name': name,
                    'token': self.current_user.token,
                    'created_at': datetime.datetime.now().replace(microsecond=0),
                    'url': f'{self.app.options.git}/raw/master/{name}'
                }
                await self.db.files.update_one({'name': name}, {'$set': doc}, upsert=True)
            else:
                self.logger.error(f'git add {name} failed: {output.decode()}')
        return p.returncode == 0

    async def git_rm(self, name):
        if not self.current_user.admin or not self.app.options.auth or not self.app.options.git:
            return False

        ret = await self.db.files.find_one_and_delete({'name': name})
        if not ret:
            self.logger.info(f'{name} not in git')
            return True

        command = f"cd '{self.root}' && git rm --cache '{name}' && git commit -m 'rm {name}' && git push origin master"
        self.logger.info(command)
        p = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await p.communicate()
        if p.returncode == 0:
            self.logger.info(f'git rm {name} succeed')
        else:
            self.logger.error(f'git rm {name} failed: {output.decode()}')
        return p.returncode == 0

    @check_auth
    async def post(self, name):
        path = self.root / name
        if self.args.action == 'delete' and self.request.headers.get('referer', '').find('/share') >= 0:
            self.logger.info(f'change action from delete to unshare')
            self.args.action = 'unshare'

        self.logger.info(f'{name}: {self.args}')
        if not path.exists() and self.args.action and self.args.action not in ['unshare', 'git-rm', 'merge']:
            self.finish({'err': 1, 'msg': f'{name} not exists'})
        elif self.args.action == 'kindle':
            if not self.current_user.kindle:
                self.finish({'err': 1, 'msg': '未设置Kindle推送邮箱'})
            elif path.is_dir():
                self.finish({'err': 1, 'msg': '不可推送文件夹'})
            elif path.stat().st_size > 52428800:
                self.finish({'err': 1, 'msg': '文件大小不可大于50MB'})
            elif not re.match('.(pdf|txt|mobi|azw|doc|docx|html|htm|rtf|jpeg|jpg|png|gif|bmp)$', path.suffix.lower()):
                self.finish({'err': 1, 'msg': '文件类型不支持推送至Kindle'})
            else:
                await self.app.email.send(self.current_user.kindle, 'convert', files=str(path))
                self.finish({'err': 0, 'msg': '推送成功'})
        elif self.args.action in ['git-add', 'git-rm']:
            if not re.match('.(gz|bz2|tar|tgz|xz|z|zip|7z|rar|mp4|mp3|exe)$', path.suffix.lower()):
                return self.finish({'err': 1, 'msg': '该扩展不可加入Git'})
            if self.args.action == 'git-add':
                ret = await self.git_add(name)
                self.finish({'err': ret, 'msg': '添加成功' if ret else '添加失败'})
            else:
                ret = await self.git_rm(name)
                self.finish({'err': ret, 'msg': '移除成功' if ret else '移除失败'})
        elif self.args.action == 'rename':
            if self.args.filename.find('/') >= 0:
                return self.finish({'err': 1, 'msg': '文件名不可包含/'})
            new_path = path.parent / self.args.filename
            if new_path.exists():
                self.finish({'err': 1, 'msg': '文件名重复'})
            else:
                path.rename(new_path)
                self.finish({'err': 0, 'msg': '重命名成功'})
        elif self.args.action == 'move':
            if self.args.dirname.startswith('/'):
                dirpath = '/'.join(self.request.path.split('/')[2:(3 if self.app.options.auth else 2)])
            else:
                dirpath = '/'.join(self.request.path.split('/')[2:- 1])
            new_path = self.root / dirpath / self.args.dirname.strip('/') / path.name
            self.logger.info(f'move {path} to {new_path}')
            if new_path.exists():
                return self.finish({'err': 1, 'msg': '目标文件已存在'})
            if new_path.parent.is_file():
                return self.finish({'err': 1, 'msg': '目标文件夹为文件'})
            new_path.parent.mkdir(parents=True, exist_ok=True)
            path.rename(new_path)
            self.finish({'err': 0, 'msg': '已移动至目标文件夹'})
        elif self.args.action == 'public':
            filename = self.root / 'public' / path.name
            if not self.current_user.admin:
                self.finish({'err': 1, 'msg': '无权限'})
            elif filename.exists():
                self.finish({'err': 1, 'msg': '{name}已存在于公共空间'})
            else:
                filename.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(path, filename)
                self.finish({'err': 0, 'msg': f'{name}已分享公共空间'})
        elif self.args.action == 'share':
            url = f'/disk/{name}'
            if not self.app.options.auth:
                return self.finish({'err': 0, 'url': url})
            doc = await self.db.share.find_one({'token': self.current_user.token, 'name': name})
            if doc and self.args.batch:
                await self.db.share.delete_one({'_id': doc._id})
                self.finish({'err': 0, 'msg': f'{name}已取消分享'})
            else:
                doc = {
                    'token': self.current_user.token,
                    'name': name,
                    'mtime': int(path.stat().st_mtime),
                    'size': path.stat().st_size,
                    'md5': await self.get_md5(path),
                    'is_dir': path.is_dir(),
                    'created_at': datetime.datetime.now().replace(microsecond=0)
                }
                if self.args.days:
                    doc['expired_at'] = doc['created_at'] + datetime.timedelta(days=int(self.args.days))
                doc = await self.db.share.find_one_and_update({'token': self.current_user.token, 'name': name},
                                                              {'$set': doc},
                                                              upsert=True,
                                                              return_document=True)
                self.finish({'err': 0, 'url': f'{url}?key={doc._id}'})
        elif self.args.action == 'unshare':
            if not self.app.options.auth:
                self.finish({'err': 0})
            else:
                await self.db.share.delete_one({'token': self.current_user.token, 'name': name})
                self.finish({'err': 0, 'msg': f'{name}已取消分享'})
        elif self.args.action == 'download':
            filename = urllib.parse.urlparse(self.args.src).path.split('/')[-1]
            filename = path / filename
            command = f"axel -n5 '{self.args.src}' -o '{filename}'"
            p = await asyncio.create_subprocess_shell(command)
            await p.wait()
            self.logger.info(f'download result: {p.returncode}, {self.args.url}')
            self.finish({'err': p.returncode, 'msg': '下载成功' if p.returncode == 0 else '下载失败'})
        elif self.args.action == 'delete':
            await self.delete(name)
        else:
            await self.upload(path)

    @check_auth
    async def delete(self, name):
        path = self.root / name
        if not path.exists():
            return self.finish({'err': 1, 'msg': f'{name} not exists'})

        if self.app.options.auth:
            await self.db.share.delete_many({'name': name})
            await self.git_rm(name)
            if not name.startswith('public'):
                for f in (self.root / 'public').rglob('*'):
                    if f.resolve() == path.absolute():
                        f.unlink()
                        await self.git_rm(str(f.relative_to(self.root)))

        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
        self.finish({'err': 0, 'msg': f'{name}删除成功'})


@bp.route(r"/chart/?(.*)")
class ChartHandler(BaseHandler):

    async def get(self, name):
        if not name:
            docs = await self.query('charts')
            self.render('chart.html', docs=docs)
        else:
            chart = await self.db.charts.find_one({'name': name})
            if not chart:
                raise tornado.web.HTTPError(404)

            if self.args.f == 'json':
                self.finish({'containers': json.loads(chart.containers)})
            else:
                self.render('chart.html')

    async def delete(self, name):
        await self.db.charts.delete_one({'name': name})
        self.finish({'err': 0})

    async def post(self, name):
        charts = json.loads(self.request.body)
        if isinstance(charts, dict):
            charts = [charts]
        containers = []
        for chart in charts:
            chart = Dict(chart)
            if chart.chart:
                chart.credits = {'enabled': False}
                containers.append(chart)
            else:
                chart.setdefault('xAxis', [])
                data = {
                    'chart': {
                        'type': chart.type,
                        'zoomType': 'x',
                    },
                    'credits': {
                        'enabled': False
                    },
                    'title': {
                        'text': chart.title,
                        'x': -20
                    },
                    'xAxis': {
                        'tickInterval': int(math.ceil(len(chart.xAxis) / 20.0)),
                        'labels': {
                            'rotation': 45 if len(chart.xAxis) > 20 else 0,
                            'style': {
                                'fontSize': 12,
                                'fontWeight': 'normal'
                            }
                        },
                        'categories': chart.xAxis
                    },
                    'yAxis': {
                        'title': {
                            'text': ''
                        },
                        'plotLines': [{
                            'value': 0,
                            'width': 1,
                            'color': '#808080'
                        }]
                    },
                    'tooltip': {
                        'headerFormat': '<span style="font-size:10px">{point.key}</span><table>',
                        'pointFormat': '<tr><td style="color:{series.color};padding:0">{series.name}: </td><td style="padding:0"><b>{point.y:.2f}</b></td></tr>',
                        'footerFormat': '</table>',
                        'shared': True,
                        'useHTML': True
                    },
                    'legend': {
                        'layout': 'horizontal',
                        'align': 'center',
                        'verticalAlign': 'bottom',
                        'borderWidth': 0,
                        'y': 0,
                        'x': 0
                    },
                    'plotOptions': {
                        'series': {
                            'marker': {
                                'radius': 1,
                                'symbol': 'diamond'
                            }
                        },
                        'pie': {
                            'allowPointSelect': True,
                            'cursor': 'pointer',
                            'dataLabels': {
                                'enabled': True,
                                'color': '#000000',
                                'connectorColor': '#000000',
                                'format': '<b>{point.name}</b>: {point.percentage:.3f} %'
                            }
                        }
                    },
                    'series': chart.series
                }
                containers.append(data)

        if containers:
            doc = {
                'name': name,
                'containers': json.dumps(containers, ensure_ascii=False),
                'charts': json.dumps(charts, ensure_ascii=False),
                'date': datetime.datetime.now().replace(microsecond=0)
            }
            await self.db.charts.update_one({'name': name}, {'$set': doc}, upsert=True)
            self.finish({'err': 0})
        else:
            self.finish({'err': 1, 'msg': '未获取到必需参数'})


@bp.route(r"/table/?(.*)")
class TableHandler(BaseHandler):

    async def get(self, name):
        if not name:
            docs = await self.query('tables')
            self.render('table.html', docs=docs)
        else:
            meta = await self.db.tables.find_one({'name': name})
            if not meta:
                raise tornado.web.HTTPError(404)

            schema = dict(map(lambda x: x.split(':'), meta['fields']))
            entries = await self.query(f'table_{name}', self.args, schema=schema)

            self.args.fields = list(map(lambda item: item.split(':')[0], meta['fields']))
            self.args.searchs = meta.get('search', [])
            self.args.marks = meta.get('mark', [])
            self.args.options = {
                'sort': self.args.fields,
                'order': ['1:asc', '-1:desc'],
            }
            self.render('table.html', entries=entries)

    async def delete(self, name):
        table = f'table_{name}'
        await self.db[table].drop()
        await self.db.tables.delete_one({'name': name})
        self.finish({'err': 0})

    async def post(self, name):
        table = f'table_{name}'
        doc = json.loads(self.request.body)
        await self.db[table].drop()
        for key in doc.get('search', []):
            await self.db[table].create_index(key)

        fields = dict(map(lambda x: x.split(':'), doc['fields']))
        if doc.get('docs'):
            dts = dict(filter(lambda x: x[1] == 'datetime', fields.items()))
            for k in dts:
                for item in doc['docs']:
                    item[k] = datetime.datetime.strptime(item[k], '%Y-%m-%d %H:%M:%S')
            await self.db[table].insert_many(doc['docs'])

        meta = {'name': name, 'date': datetime.datetime.now().replace(microsecond=0)}
        meta.update(dict(filter(lambda x: x[0] in ['fields', 'search', 'mark'], doc.items())))
        await self.db.tables.update_one({'name': name}, {'$set': meta}, upsert=True)
        self.finish({'err': 0})

    async def put(self, name):
        table = f'table_{name}'
        doc = json.loads(self.request.body)
        meta = await self.db.tables.find_one({'name': name})
        type_dict = dict(map(lambda x: x.split(':'), meta['fields']))
        if type_dict[doc['key']] == 'int':
            doc['value'] = int(doc['value'])
        elif type_dict[doc['key']] == 'float':
            doc['value'] = float(doc['value'])
        elif type_dict[doc['key']] == 'datetime':
            doc['value'] = datetime.datetime.strptime(doc['value'], '%Y-%m-%d %H:%M:%S')

        if doc['action'] == 'add':
            op = '$set' if doc.get('unique') else '$addToSet'
        else:
            op = '$unset' if doc.get('unique') else '$pull'
        await self.db[table].update_one({'_id': ObjectId(doc['_id'])}, {op: {doc['key']: doc['value']}})
        self.finish({'err': 0})
