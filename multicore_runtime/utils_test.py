# Copyright 2015 Google Inc. All Rights Reserved.
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
import gc
import httplib
from multiprocessing.pool import ThreadPool
import os
import threading
import unittest
import uuid
import weakref

from . import wsgi_config
from . import utils

from mock import MagicMock
from mock import patch
from werkzeug import datastructures
from werkzeug import http
from werkzeug import test
from werkzeug import wrappers

from google.appengine.api import appinfo


def script_path(script, test_name=__name__):
  """Returns a fully qualified module path based on test_name."""
  return '{test_path}.{script}'.format(
      test_path=test_name, script=script)

FAKE_HANDLERS = [
    appinfo.URLMap(url='/hello', script=script_path('hello_world')),
    appinfo.URLMap(url='/setcallback', script=script_path('setup_callback')),
    appinfo.URLMap(url='/testlocal', script=script_path('test_local')),
    appinfo.URLMap(url='/testlocal2', script=script_path('test_local2')),
    appinfo.URLMap(url='/testmemory', script=script_path('test_memory')),
    appinfo.URLMap(url='/testmemory_init',
                   script=script_path('test_memory_with_init')),
    appinfo.URLMap(url='/test_init_attributes',
                   script=script_path('test_args_init')),
    appinfo.URLMap(url='/wait', script=script_path('wait_on_global_event')),
    appinfo.URLMap(url='/check', script=script_path('check_concurrent_attribute')),
    appinfo.URLMap(url='/add_to_class_attr', script=script_path('add_to_class_attr')),
    appinfo.URLMap(url='/test_class_attr', script=script_path('test_class_attr')),
    ]

HELLO_STRING = 'Hello World!'
FAKE_ENV_VARIABLES = {'KEY': 'VALUE',
                      'USER_EMAIL': 'what@example.com'}

FAKE_APPINFO_EXTERNAL = MagicMock(handlers=FAKE_HANDLERS,
                                  env_variables=FAKE_ENV_VARIABLES)

FAKE_APPENGINE_CONFIG = MagicMock(
    server_software='server', partition='partition', appid='appid',
    module='module', instance='instance', major_version='major',
    minor_version='minor', default_ticket='ticket')

REQ_HEADER = 'HTTP_X_APPENGINE_REQUEST_ID_HASH'

# Global objects used for tests
class State(utils.RequestLocal):
  pass

class A():
  pass

class Blob(utils.RequestLocal):
  def __init__(self):
    self.data = set()

class ClassVars(utils.RequestLocal):
  info = set()

state = State()
blob = Blob()
classvars = ClassVars()
callback_called = False
ref_list = []
concurrent_request_is_started = threading.Event()
concurrent_request_should_proceed = threading.Event()


@wrappers.Request.application
def hello_world(request):  # pylint: disable=unused-argument
  return wrappers.Response(HELLO_STRING)

@wrappers.Request.application
def setup_callback(request):
  def callback():
    global callback_called
    callback_called = True

  utils.SetRequestEndCallback(callback)
  return wrappers.Response("pass!")

@wrappers.Request.application
def test_local(request):
  state.test = True
  return wrappers.Response("pass!")

@wrappers.Request.application
def test_local2(request):
  if hasattr(state, 'test'):
    return wrappers.Response(status=404)
  else:
    return wrappers.Response("pass!")

@wrappers.Request.application
def test_memory(request):
  a = A()
  ref_list.append(weakref.ref(a))
  state.stuff = a
  return wrappers.Response("pass!")

@wrappers.Request.application
def test_memory_with_init(request):
  ref_list.append(weakref.ref(blob.data))
  return wrappers.Response("pass!")

@wrappers.Request.application
def test_args_init(request):
  if hasattr(blob, 'data') and isinstance(blob.data, set):
    return wrappers.Response("pass!")
  return wrappers.Response(status=404)

@wrappers.Request.application
def wait_on_global_event(request):
  state.testing = True
  concurrent_request_is_started.set()
  concurrent_request_should_proceed.wait()
  return wrappers.Response("pass!")

@wrappers.Request.application
def check_concurrent_attribute(request):
  if hasattr(state, 'testing'):
    return wrappers.Response(status=404)
  else:
    return wrappers.Response("pass!")

@wrappers.Request.application
def add_to_class_attr(request):
  a = A()
  ref = weakref.ref(a)
  classvars.info.add(a)
  ref_list.append(a)
  return wrappers.Response("pass!")

@wrappers.Request.application
def test_class_attr(request):
  if classvars.info:
    return wrappers.Response(status=404)
  else:
    return wrappers.Response("pass!")


class MetaAppTestCase(unittest.TestCase):

  def setUp(self):
    # pylint: disable=g-import-not-at-top
    # Pre-import modules to patch them in advance.
    from google.appengine.ext.vmruntime import vmconfig


    # Instantiate an app with a simple fake configuration.
    with patch.object(wsgi_config, 'get_module_config_filename'):
      with patch.object(wsgi_config, 'get_module_config',
                        return_value=FAKE_APPINFO_EXTERNAL):
        with patch.object(vmconfig, 'BuildVmAppengineEnvConfig',
                          return_value=FAKE_APPENGINE_CONFIG):
          import wsgi
          self.app = wsgi.meta_app

    self.headers = datastructures.Headers(
        {REQ_HEADER: str(uuid.uuid4())})
    self.client = test.Client(self.app, wrappers.Response)
    self.spare_client = test.Client(self.app, wrappers.Response)

  def tearDown(self):
    global ref_list
    ref_list = []

  def test_hello(self):
    response = self.client.get('/hello')
    self.assertEqual(response.status_code, httplib.OK)
    self.assertEqual(response.data, HELLO_STRING)

  # Tests ability to set a callback that is invoked when the request ends
  def test_request_callback(self):
    response = self.client.get('/setcallback', headers=self.headers)
    self.assertEqual(response.status_code, httplib.OK)
    self.assertTrue(callback_called)

  def test_request_local_attributes_not_shared(self):
    response = self.client.get('/testlocal', headers = self.headers)
    self.assertEqual(response.status_code, httplib.OK)
    self.headers.add(REQ_HEADER, str(uuid.uuid4()))
    response = self.client.get('/testlocal2', headers = self.headers)
    self.assertEqual(response.status_code, httplib.OK)

  def test_concurrent_requests(self):
    # Same test as above but both requests occur at the same time

    pool = ThreadPool(processes=1)
    future = pool.apply_async(self.client.get, ('/wait',))

    success = concurrent_request_is_started.wait(5)
    self.assertTrue(success) # Makre sure first request is ongoing
    response = self.spare_client.get('/check')
    self.assertEquals(response.status_code, httplib.OK)

    concurrent_request_should_proceed.set()
    response = future.get(5)
    self.assertEqual(response.status_code, httplib.OK)


  def test_request_local_deleted_when_request_ends(self):
    response = self.client.get('/testmemory', headers = self.headers)
    self.assertEqual(response.status_code, httplib.OK)
    gc.collect()
    for ref in ref_list:
      self.assertEqual(ref(), None)

  def test_request_local_with_init(self):
    # This actually does 2 tests
    # 1. Initialized attributes are cleaned up when a request ends
    # 2. Initialized attributes are available when a new request starts
    response = self.client.get('/testmemory_init', headers = self.headers)
    self.assertEqual(response.status_code, httplib.OK)
    gc.collect()
    for ref in ref_list:
      self.assertEqual(ref(), None)

    # This is test 2
    self.headers.add(REQ_HEADER, str(uuid.uuid4()))
    response = self.client.get('/test_init_attributes', headers = self.headers)
    self.assertEqual(response.status_code, httplib.OK)

