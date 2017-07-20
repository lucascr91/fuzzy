import os
import json
import argparse
import traceback
import subprocess as sub
import shutil

import tornado.ioloop
import tornado.web
import tornado.websocket

# parse input arguments
parser = argparse.ArgumentParser(description='Mnemonic Server.')
parser.add_argument('--path', type=str, help='location of files')
parser.add_argument('--port', type=int, default=9020, help='port to serve on')
parser.add_argument('--tag', type=str, default='#', help='tag indicator')
parser.add_argument('--sep', type=bool, default=False, help='put tags on next line')
args = parser.parse_args()

# hardcoded
tmp_dir = 'temp'
max_len = 90
max_res = 100

# search tools
cmd = 'ag --nobreak --noheading ".+" "%(path)s" | fzf -f "%(words)s" | head -n %(max_res)d'

# searching
def search(words):
    query = cmd % dict(path=args.path, words=words, max_res=max_res)
    with sub.Popen(query, shell=True, stdout=sub.PIPE) as proc:
        outp, _ = proc.communicate()
        print(outp)
        for line in outp.decode().split('\n'):
            if len(line) > 0:
                fpath, line, text = line.split(':', maxsplit=2)
                fname = os.path.basename(fpath)
                if len(text) > max_len - 3:
                    text = text[:max_len-3] + '...'
                yield {'file': fname, 'line': line, 'text': text}


# text tools
def bsplit(s, sep='\n'):
    if sep not in s:
        return s, ''
    else:
        return s.split(sep, maxsplit=1)


class EditorHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("editor.html")


class FuzzyHandler(tornado.websocket.WebSocketHandler):
    def initialize(self):
        print("initializing")
        self.results = None

    def allow_draft76(self):
        return True

    def open(self):
        print("connection received")

    def on_close(self):
        print("connection closing")

    def error_msg(self, error_code):
        if error_code is not None:
            json_string = json.dumps({"type": "error", "code": error_code})
            self.write_message("{0}".format(json_string))
        else:
            print("error code not found")

    def write_json(self, js):
        self.write_message(json.dumps(js))

    def on_message(self, msg):
        try:
            print(u'received message: {0}'.format(msg))
        except Exception as e:
            print(e)
        data = json.loads(msg)
        (cmd, cont) = (data['cmd'], data['content'])
        if cmd == 'query':
            try:
                print('Query: ' + cont)
                ret = list(search(cont))
                self.write_json({'cmd': 'results', 'content': ret})
            except Exception as e:
                print(e)
                print(traceback.format_exc())
        elif cmd == 'text':
            try:
                print('Loading: ' + cont)
                fpath = os.path.join(args.path, cont)
                with open(fpath) as fid:
                    text = fid.read()
                    if args.sep:
                        title, rest = bsplit(text)
                        if rest.lstrip().startswith(args.tag):
                            tags, body = bsplit(rest.lstrip())
                            tags = [s[1:] for s in tags.split() if s.startswith(args.tag)]
                        else:
                            body = rest
                        body = body[1:] if body.startswith('\n') else body
                    else:
                        head, body = bsplit(text[1:])
                        head = head.split()
                        title = ' '.join([s for s in head if not s.startswith(args.tag)])
                        tags = [s[1:] for s in head if s.startswith(args.tag)]
                        body = body[1:] if body.startswith('\n') else body
                    self.write_json({'cmd': 'text', 'content': {'file': cont, 'title': title, 'tags': tags, 'body': body}})
            except Exception as e:
                print(e)
                print(traceback.format_exc())
        elif cmd == 'save':
            try:
                tags = ' '.join([args.tag + t for t in cont['tags']])
                text = '!' + cont['title'] + ' ' + tags + '\n\n' + cont['body']

                fname = cont['file']
                tpath = os.path.join(tmp_dir, fname)
                fpath = os.path.join(args.path, fname)

                fid = open(tpath, 'w+')
                fid.write(text)
                fid.close()
                shutil.move(tpath, fpath)
            except Exception as e:
                print(e)
                print(traceback.format_exc())


# tornado content handlers
class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", EditorHandler),
            (r"/fuzzy", FuzzyHandler)
        ]
        settings = dict(
            app_name=u"Fuzzy Editor",
            template_path="templates",
            static_path="static",
            xsrf_cookies=True,
        )
        tornado.web.Application.__init__(self, handlers, debug=True, **settings)


# create server
application = Application()
application.listen(args.port)
tornado.ioloop.IOLoop.current().start()
