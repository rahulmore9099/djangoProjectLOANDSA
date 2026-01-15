import os
import sys

path = '/home/<your-username>/bank_chatbot'
if path not in sys.path:
    sys.path.append(path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'bank_chatbot.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
