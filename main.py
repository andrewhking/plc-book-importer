#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Starting template for Google App Engine applications.

Use this project as a starting point if you are just beginning to build a Google
App Engine project. Remember to download the OAuth 2.0 client secrets which can
be obtained from the Developer Console <https://code.google.com/apis/console/>
and save them as 'client_secrets.json' in the project directory.
"""

__author__ = 'jcgregorio@google.com (Joe Gregorio)'


import httplib2
import logging
import os
import pickle
import urllib

from apiclient import discovery
from oauth2client import appengine
from oauth2client import client
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import ndb

import webapp2
import jinja2
import cgi
import json
import re
import time
import urllib

API_KEY="AIzaSyBF2cNrp5RfP6sH4IZJSsH0U9PP5fIv64s"
BOOKS_API = "https://www.googleapis.com/books/v1/volumes?q=isbn:%(isbn)s&key=%(api_key)s&country=US"
LIBRARY_API = "https://www.googleapis.com/books/v1/mylibrary/bookshelves?key=%(api_key)s&country=US"

DEFAULT_LIBRARY_NAME = 'default_library'
API_KEY="AIzaSyBF2cNrp5RfP6sH4IZJSsH0U9PP5fIv64s"
JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    autoescape=True,
    extensions=['jinja2.ext.autoescape'])

# CLIENT_SECRETS, name of a file containing the OAuth 2.0 information for this
# application, including client_id and client_secret, which are found
# on the API Access tab on the Google APIs
# Console <http://code.google.com/apis/console>
CLIENT_SECRETS = os.path.join(os.path.dirname(__file__), 'client_secrets.json')

# Helpful message to display in the browser if the CLIENT_SECRETS file
# is missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
<h1>Warning: Please configure OAuth 2.0</h1>
<p>
To make this sample run you will need to populate the client_secrets.json file
found at:
</p>
<p>
<code>%s</code>.
</p>
<p>with information found on the <a
href="https://code.google.com/apis/console">APIs Console</a>.
</p>
""" % CLIENT_SECRETS

MAIN_PAGE_FOOTER_TEMPLATE = """\
    <form action="/library?%s" method="post">
      <div><input type=text name="isbn" rows="1" cols="60"></textarea></div>
    </form>

    <hr>

    <form>Library name:
      <input value="%s" name="library_name">
      <input type="submit" value="switch">
    </form>

    <a href="%s">%s</a>

  </body>
</html>
"""

def library_key(library_name=DEFAULT_LIBRARY_NAME):
    """Constructs a Datastore key for a Library entity with library_name."""
    return ndb.Key('Library', library_name)


class Book(ndb.Model):
    """Models an individual Library entry with author, content, and date."""
    isbn = ndb.StringProperty(indexed=False)
    authors = ndb.StringProperty(indexed=False)
    title = ndb.StringProperty(indexed=False)
    date = ndb.DateTimeProperty(auto_now_add=True)

http = httplib2.Http(memcache)
service = discovery.build("books", "v1", http=http, developerKey=API_KEY)
decorator = appengine.oauth2decorator_from_clientsecrets(
    CLIENT_SECRETS,
    scope='https://www.googleapis.com/auth/books',
    message=MISSING_CLIENT_SECRETS_MESSAGE)

class AuthHandler(webapp2.RequestHandler):

  @decorator.oauth_aware
  def get(self):
    variables = {
        'url': decorator.authorize_url(),
        'has_credentials': decorator.has_credentials()
        }
    if variables['has_credentials']:
      self.redirect('/main')
    else:
      template = JINJA_ENVIRONMENT.get_template('grant.html')
      self.response.write(template.render(variables))


class LibraryHandler(webapp2.RequestHandler):

  @decorator.oauth_required
  def post(self):
    try:
      # We set the same parent key on the 'Book' to ensure each Book
      # is in the same entity group. Queries across the single entity group
      # will be consistent. However, the write rate to a single entity group
      # should be limited to ~1/second.
      library_name = self.request.get('library_name',
                                      DEFAULT_LIBRARY_NAME)
      book = Book(parent=library_key(library_name))
      book.isbn = self.request.get('isbn')

      resp, data = http.request(BOOKS_API % {'isbn': book.isbn, 'api_key': API_KEY})
      data = json.loads(data)

      resp, library_data = http.request(LIBRARY_API % {'api_key': API_KEY})
      library_data = json.loads(library_data)
      print library_data

      if data['totalItems'] == 1:
        title = data['items'][0]['volumeInfo']['title']
        authors = ','.join(data['items'][0]['volumeInfo']['authors'])
        
        book.authors = authors
        book.title = title
        if book.title:
          book.put()

      query_params = {'library_name': library_name}
      self.redirect('/?' + urllib.urlencode(query_params))
    except client.AccessTokenRefreshError:
      self.redirect('/main')

class MainPage(webapp2.RequestHandler):

  @decorator.oauth_required
  def get(self):
    try:
      http = decorator.http()
      user = users.get_current_user()
      self.response.write('<html><body>')

      library_name = self.request.get('library_name',
                                      DEFAULT_LIBRARY_NAME)

      # Ancestor Queries, as shown here, are strongly consistent with the High
      # Replication Datastore. Queries that span entity groups are eventually
      # consistent. If we omitted the ancestor from this query there would be
      # a slight chance that Book that had just been written would not
      # show up in a query.
      books_query = Book.query(
        ancestor=library_key(library_name)).order(-Book.date)
      books = books_query.fetch(10)
      user_id = users.get_current_user().user_id()
      print user_id
      
      for book in books:
        if book.authors:
          self.response.write('<b>%s: %s</b>' % (cgi.escape(book.authors), cgi.escape(book.title)))
          self.response.write('<blockquote>%s</blockquote>' % cgi.escape(book.isbn))

      print 'NumBooks: %s' %len(books)
      if users.get_current_user():
        url = users.create_logout_url(self.request.uri)
        url_linktext = 'Logout'
      else:
        url = users.create_login_url(self.request.uri)
        url_linktext = 'Login'

      # Write the submission form and the footer of the page
      scan_query_params = urllib.urlencode({'library_name': library_name})
      self.response.write(MAIN_PAGE_FOOTER_TEMPLATE %
                          (scan_query_params, cgi.escape(library_name),
                           url, url_linktext))

    except client.AccessTokenRefreshError:
      self.redirect('/')



app = webapp2.WSGIApplication(
    [
     ('/', AuthHandler),
     ('/main', MainPage),
     ('/library', LibraryHandler),
     (decorator.callback_path, decorator.callback_handler()),
    ],
    debug=True)
