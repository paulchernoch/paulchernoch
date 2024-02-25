import os
import sys
from typing import Tuple, List
from http.server import HTTPServer
from http.server import SimpleHTTPRequestHandler

# Default error message template
DEFAULT_ERROR_MESSAGE = """\
<head>
<title>Error response</title>
</head>
<body>
<h1>Error response for HTTP request</h1>
<p>Error code %(code)d.
<p>Message: %(message)s.
<p>Error code explanation: %(code)s = %(explain)s.
</body>
"""

def load_file(filename: str, default_contents: str) -> Tuple[bool,str]:
  contents = default_contents
  success = False
  try:
      with open(filename) as f:
          success = True
          contents = f.read()
  except OSError as e:
      success = False
  return (success, contents)

loading_ok, HTTP_ERROR_TEMPLATE = load_file("404.html", DEFAULT_ERROR_MESSAGE)

if not loading_ok:
    print("Missing file: 404.html")


class MyHandler(SimpleHTTPRequestHandler):
    def send_error(self, code, message=None):
        if code == 404:
            self.error_message_format = HTTP_ERROR_TEMPLATE
        SimpleHTTPRequestHandler.send_error(self, code, message)


port = 8000
if len(sys.argv) > 1:
    port = int(sys.argv[1])

if __name__ == '__main__':
    httpd = HTTPServer(('', port), MyHandler)
    print(f"Serving app on port {port} ...")
    httpd.serve_forever()

  