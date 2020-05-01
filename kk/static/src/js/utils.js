if (!Object.keys) {
  Object.keys = function (o) {
    if (o !== Object(o)) {
      throw new TypeError('Object.keys called on a non-object')
    }
    var k = [];
    var p
    for (p in o)
      if (Object.prototype.hasOwnProperty.call(o, p)) k.push(p)
    return k
  }
}
if (!Object.values) {
  Object.values = function (obj) {
    if (obj !== Object(obj)) {
      throw new TypeError('Object.values called on a non-object')
    }
    var val = [];
    var key
    for (key in obj) {
      if (Object.prototype.hasOwnProperty.call(obj, key)) {
        val.push(obj[key])
      }
    }
    return val
  }
}
String.prototype.format = function () {
  var args = arguments
  return this.replace(/{(\d+)}/g, function (match, number) {
    return typeof args[number] !== 'undefined' ? args[number] : match
  })
}
function getCookie(name) {
  var r = document.cookie.match('\\b' + name + '=([^;]*)\\b')
  return r ? r[1] : undefined
}
function setCookie(name, value, expires_days) {
  var domain = location.host.split(':')[0]
  if (expires_days) {
    var exp = new Date()
    exp.setTime(exp.getTime() + expires_days * 86400000 + 8 * 3600000)
    document.cookie = name + '=' + value + ';path=/;domain=' + domain + ';expires=' + exp.toUTCString()
  } else {
    document.cookie = name + '=' + value + ';path=/;domain=' + domain + ';'
  }
}
function removeCookie(name) {
  setCookie(name, '', -1)
}
function parseUrl(url) {
  var a = document.createElement('a');
  a.href = url || location.href;
  return {
    source: url,
    protocol: a.protocol.replace(':',''),
    host: a.hostname,
    port: a.port,
    query: a.search,
    params: (function(){
      var ret = {},
        seg = a.search.replace(/^\?/,'').split('&'),
        len = seg.length, i = 0, s;
      for (;i<len;i++) {
        if (!seg[i]) { continue; }
        s = seg[i].split('=');
        ret[s[0]] = decodeURIComponent(s[1]).replace('+', ' ');
      }
      return ret;
    })(),
    // file: (a.pathname.match(/\/([^\/?#]+)$/i) || [,''])[1],
    // relative: (a.href.match(/tps?:\/\/[^\/]+(.+)/) || [,''])[1],
    hash: a.hash.replace('#',''),
    path: a.pathname.replace(/^([^\/])/,'/$1'),
    segments: a.pathname.replace(/^\//,'').split('/')
  }
}
