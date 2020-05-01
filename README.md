![](https://img.shields.io/badge/author-digua-blue)
![](https://img.shields.io/github/license/zkdfbb/kk)
![](https://img.shields.io/pypi/v/kk)
![](https://img.shields.io/pypi/pyversions/kk)

### 1. 主要功能

1. 支持用作简单文件列表，无需数据库，无用户管理，分享等功能
2. 支持基本网盘功能，需要安装MongoDB及Redis，支持用户注册，文件分享，用户目录可设置公开访问，公共目录等功能
3. 用户可设置自己的目录是否完全公开，公开时所有人都可访问，但无法修改文件
4. 公共目录内的文件只有管理员可管理，所有人都可公开访问，但无法修改文件
5.  大文件分片上传，文件夹上传，剪切板粘贴上传图片
6.  离线下载，需要安装`axel`，可粘贴`http/https`链接进行下载
7.  批量删除、批量分享至公共空间、批量分享、批量取消分享
8.  预览功能，支持`.sh` `.py` `.java` `.c` `.js` `.css` 等代码预览，且支持代码高亮，支持`.jpg` `.txt` `.pdf` `.md`, `.html` 等文件格式预览，支持`.zip` `.tar.gz` `.tar.bz2`等压缩格式预览，在可外网访问的环境下，支持`.docx` `.xlsx` `.pptx`等Office文件预览
9.  播放功能，支持`.mp4` `.flv` `.m3u8` 等视频格式播放，支持`.mp3` `.wav` `.ogg` 等音频格式播放
10.  推送功能，支持将`.mobi` `.epub` `.pdf` `.txt`等Kindle支持的文件推送至Kindle
11.  文件下载，支持文件夹压缩下载
12.  支持实时预览，可切换文件列表模式及预览模式（直接打开图片，播放音乐）
13.  支持列表及图标布局，图标布局模式下采用瀑布流加载
14.  支持切换显示树形目录
15.  支持文件搜索，若采用网盘模式时只搜索当前目录及子目录下的文件，否则搜索全部文件

### 安装部署

确保您的`Python`版本>=3.6，一键安装方式如下
```bash
pip install kk    # 安装
kk                # 运行
```

若采用网盘模式启动，需先安装`MongoDB`及`Redis`，推荐使用`docker`进行安装，同时设置必要的环境变量

若`MongoDB`有密码，如用户名密码为`admin/123456`，则需设置环境变量`MONGO_URI`
```bash
export MONGO_URI=mongodb://admin:123456@localhost:27017/admin
```

若`Redis`有密码，如密码为123456，则需设置环境变量`REDIS_URI`
```bash
export REDIS_URI=redis://:123456@localhost:6379
```

要发送邮件，需先设置邮件服务器相关的环境变量
```bash
export EMAIL_SENDER=
export EMAIL_SMTP=
export EMAIL_USER=
export EMAIL_PWD=
```

然后再以网盘模式启动
```bash
kk --auth=true
```

本源码使用的默认数据库名为`kk`，第一个注册的用户即为管理员，建议对如下字段建立索引
```
db.share.ensureIndex({token: 1})
db.share.ensureIndex({name: 1})
db.users.ensureIndex({id: 1}, {unique: 1})
db.users.ensureIndex({username: 1}, {unique: 1})
db.users.ensureIndex({email: 1}, {unique: 1})
```

其他可选参数
```
--auth=true   # 以网盘模式启动
--tools=true  # 显示工具箱，用于画图及制表
--root=.      # 设置根目录，默认为当前文件夹
--db=kk       # 设置数据库名称，默认为kk
```
