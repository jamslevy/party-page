import cgi
import os
import sys
import urllib, urllib2
import logging
import pickle

from google.appengine.api import users
from google.appengine.api import oauth
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.api import memcache
import gravatar
from django.utils import simplejson
from datetime import datetime
import models
# Set the debug level
_DEBUG = True

class BaseRequestHandler(webapp.RequestHandler):
  """Base request handler extends webapp.Request handler

     It defines the generate method, which renders a Django template
     in response to a web request
  """
  def json(self, obj):
    """Json takes an object and returns it through the response object of the
       current request.
       
       Args:
            obj is the object we are going to send. It should be fully ready to get 
            converted into json and sent down.          
    """
    self.response.out.write(simplejson.dumps(obj))

  def generate(self, template_name, template_values={}):
    """Generate takes renders and HTML template along with values
       passed to that template

       Args:
         template_name: A string that represents the name of the HTML template
         template_values: A dictionary that associates objects with a string
           assigned to that object to call in the HTML template.  The defualt
           is an empty dictionary.
    """
    # We check if there is a current user and generate a login or logout URL
    user = users.get_current_user()
    ouser = oauth.get_current_user()
    if user or ouser:
      log_in_out_url = users.create_logout_url('/') 
    else:
      log_in_out_url = users.create_login_url(self.request.path) #we need to shuttle them back where they came from in this instance

    # We'll display the user name if available and the URL on all pages
    values = {'user': user, 'log_in_out_url': log_in_out_url}
    values.update(template_values)

    # Construct the path to the template
    directory = os.path.dirname(__file__)
    path = os.path.join(directory, 'templates', template_name)

    # Respond to the request by rendering the template
    return template.render(path, values, debug=_DEBUG)


class IndexRequestHandler(BaseRequestHandler):

  def get(self):
    self.response.out.write(self.generate('index.html'))
    
        
class iFrameRequestHandler(BaseRequestHandler):

  def get(self):
    user = users.get_current_user()
    self.response.out.write(self.generate('iframe.html',
    { "user": users.get_current_user() }))
    
class EmbedRequestHandler(BaseRequestHandler):

  def get(self):
    import config
    template_values = {
        "SERVER_HOST": config.SERVER_HOST
    }
    self.response.out.write(self.generate('embed.html', template_values))
    

class WidgetJSHandler(BaseRequestHandler):

  def get(self):
    import config
    from utils import cssmin 
    template_values = {
        "SERVER_HOST": config.SERVER_HOST,
        "css": cssmin.cssmin(self.generate('party_page_widget.css', {})).replace('\n','').replace("'",'"')
    }
    if not users.get_current_user():
      template_values['login_url'] = users.create_login_url(self.request.get('gowith'))
    self.response.headers['Content-Type'] = "application/javascript"
    self.response.out.write(self.generate('party_page_widget.js', template_values))
    
        

class ChatsRequestHandler(BaseRequestHandler):
  MEMCACHE_KEY = 'partypage'
  MEMCACHE_TEMPLATE = 'partypage_template'
  
  def get(self):
    chat_url = urllib2.unquote(self.request.get('url'))
    author = users.get_current_user()
    logging.info(chat_url)
    session = models.ChatSession.get(chat_url, author)
    template = memcache.get(self.MEMCACHE_TEMPLATE + str(session.key()))
    self.response.out.write(template)
    
  def post(self):
    chat = models.ChatMessage()

    author = users.get_current_user()
    if author:
      chat.author = author
    
    chat.content = self.request.get('content')
    
    
    cfs = ['', 'I love you! I have always loved you. There. I said it.', '', 
      ' I sometimes wear a bowtie in the shower.', '', 'My spirit animal is a nudist pirate named Karl.', 
      '', 'Just shut up. I am so sick and tired of you. SERIOUSLY. ', '', 'my ding ding hurts', '', 
      ' Do u w4nna cyb3r?', '', '', '', '' 'I have eight husbands and a one legged parakeet.', 
      '', 'I like making sweet love to Peruvian lamas.', 'HAI! I CAN HAZ A HUGZ?'
      'You had me at "Hello World."', 'How about we go home and you handle my exception?'
      ] 
    import random
    if False:
        c = random.choice(cfs)
        if c: chat.content += (' ' + c)
    
    
    chat_url = urllib2.unquote(self.request.get('url'))
    chat.session = models.ChatSession.get(chat_url, author)
    chat.put()
    
    chatsString = memcache.get(self.MEMCACHE_KEY + str(chat.session.key()))
    if chatsString is None:
      chatsList = []
    else:
      chatsList = pickle.loads(chatsString)
      if chatsList and len(chatsList) >= 100:
        chatsList.pop(0)
    chatsList.insert(0, chat)
    
    import datetime
    last_time = datetime.datetime.fromtimestamp(0)
    for msg in chatsList:
        logging.info(last_time + datetime.timedelta(seconds=120))
        logging.info(msg.date - (last_time + datetime.timedelta(seconds=120)))
        if msg.date > last_time + datetime.timedelta(seconds=120):
            msg.natural_date = (msg.date - datetime.timedelta(hours=7)).strftime("%I:%M%p - %A %B %d, %Y")
        last_time = msg.date
    if not memcache.set(self.MEMCACHE_KEY + str(chat.session.key()), pickle.dumps(chatsList)):
        logging.debug("Memcache set failed:")  
    
    template_values = {
      'chats': chatsList,
    }
    
    template = self.generate('chats.html', template_values)
    if not memcache.set(self.MEMCACHE_TEMPLATE + str(chat.session.key()), template):
        logging.debug("Memcache set failed:")          
    
    self.response.out.write(template)

    
class EditUserProfileHandler(BaseRequestHandler):
  """This allows a user to edit his or her profile.  The user can upload
     a picture and set a feed URL for personal data
  """
  def get(self, user):
    # Get the user information
    unescaped_user = urllib.unquote(user)
    user_object = users.User(unescaped_user)
    # Only that user can edit his or her profile
    if users.get_current_user() != user_object:
      self.redirect('/view/StartPage')

    user = models.ChatUser.gql('WHERE user = :1', user_object).get()
    if not user:
      user = models.ChatUser(user=user_object)
      user.put()

    self.response.out.write(self.generate('edit_user.html', template_values={'queried_user': user}))

  def post(self, user):
    # Get the user information
    unescaped_user = urllib.unquote(user)
    user_object = users.User(unescaped_user)
    # Only that user can edit his or her profile
    if users.get_current_user() != user_object:
      self.redirect('/')

    user = models.ChatUser.gql('WHERE user = :1', user_object).get()

    user.picture = self.request.get('user_picture')
    user.website = self.request.get('user_website')
    user.put()


    self.redirect('/user/%s' % user)
    
class UserProfileHandler(BaseRequestHandler):
  """Allows a user to view another user's profile.  All users are able to
     view this information by requesting http://wikiapp.appspot.com/user/*
  """

  def get(self, user):
    """When requesting the URL, we find out that user's WikiUser information.
       We also retrieve articles written by the user
    """
    # Webob over quotes the request URI, so we have to unquote twice
    unescaped_user = urllib.unquote(urllib.unquote(user))

    # Query for the user information
    user_object = users.User(unescaped_user)
    user = models.ChatUser.gql('WHERE user = :1', user_object).get()

    # Generate the user profile
    self.response.out.write(self.generate('user.html', template_values={'queried_user': user}))

    
class SendInvitesHandler(BaseRequestHandler):
  """ Process posted event form 
  """
  def post(self):
    from google.appengine.api import mail
    emails = self.request.get('emails').split(',')
    for invite_email in emails:
      mail.send_mail(sender=self.request.get('user'),
              to=invite_email,
              subject="You're invited to a party!",
              body="""
              
              Hey, you're invited to a party on a webpage!
              
              Visit this web address to join:
              
              %s
              
              If you don't see a "party!" tab on the right side of the page, 
              make sure you're using the Google Chrome browser and 
              install the Party Page! extension from this address:
              
              %s
              
              """ % (self.request.get("url"), "http://page-party.appspot.com"))

class RPCHandler(webapp.RequestHandler):
  def __init__(self):
    webapp.RequestHandler.__init__(self)
    self.methods = RPCMethods()
  def post(self):
    args = simplejson.loads(self.request.body)
    func, args = args[0], args[1:]
    
    if func[0] == '_':
      self.error(403)
      return
    func = getattr(self.methods, func, None)
    if not func:
      self.error(404)
      return
    result = func(self.request, *args)
    self.response.out.write(simplejson.dumps(result))

class RPCMethods:
  
  def chat(self, request, domain, message):
    chat = models.ChatMessage()
    author = users.get_current_user() if users.get_current_user() else oauth.get_current_user()
    if author:
      chat.author = author
    chat_url = urllib2.unquote(domain)
    chat.content = message
    chat.session = models.ChatSession.get(chat_url, author)
    chat.put()
    def chatToJson(x):
      g = gravatar.gravatar(x.author.email(), json=True)
      return {'id': x.key().id(),'author':{'nickname':x.author.nickname(),'email':x.author.email()},'thumb':g, 'content':x.content,'date':datetime.ctime(x.date)}
    c = chatToJson(chat)
    return({'success':True, 'message': c})
    
  def getchat(self,request, domain, timestamp = 0):
    def to_datetime(js_timestamp):
      return  datetime.fromtimestamp(js_timestamp/1000, None)
    chat_url = urllib2.unquote(domain)
    author = users.get_current_user()
    # logging.info(chat_url)
    session = models.ChatSession.get(chat_url, author)
    try:
      chats = models.ChatMessage.getsince(to_datetime(timestamp), session)
      def chat_to_dict(x):
        g = gravatar.gravatar(x.author.email(), json=True)
        return {'author':{'nickname':x.author.nickname(),'email':x.author.email()},'thumb':g,'content':x.content, 'date':datetime.ctime(x.date), 'id':x.key().id()}
      result = map(chat_to_dict, chats)
      return {'success':True, 'result':result, 'query':{'date':timestamp,'url':domain}}
    except:
      return {'success':False, 'query':{'date':timestamp,'url':domain}, 'error':sys.exc_info()[1].message}
  def sendmail(self,request, domain, *emails):
    from google.appengine.api import mail
    for invite_email in emails:
      try:
        mail.send_mail(sender=users.get_current_user().email(), to=invite_email, subject="You're invited to a party!", body="""
          
          Hey, you're invited to a party on a webpage!
          
          Visit this web address to join:
          
          %s
          
          If you don't see a "party!" tab on the right side of the page, 
          make sure you're using the Google Chrome browser and 
          install the Party Page! extension from this address:
          
          %s
          
          """ % (domain, "http://page-party.appspot.com"))
        return{'success':True,'recipients':emails}
      except:
        return{'success':False,'error':sys.exc_info[1].message}
      

application = webapp.WSGIApplication(
                                     [('/', IndexRequestHandler),
                                      ('/rpc*', RPCHandler),
                                      ('/iframe', iFrameRequestHandler),
                                      ('/embed', EmbedRequestHandler),
                                      ('/embed2', EmbedRequestHandler),
                                      ('/party-page-js', WidgetJSHandler),
                                      ('/getchats', ChatsRequestHandler),
                                      ('/sendinvites', SendInvitesHandler),
                                      ('/user/([^/]+)', UserProfileHandler),
                                      ('/edituser/([^/]+)', EditUserProfileHandler)],
                                     debug=True)

def main():
  run_wsgi_app(application)

template.register_template_library('gravatar')
if __name__ == "__main__":
  main()