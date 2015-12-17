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
"""Utilities provided by the runtime"""

import os
import thread
import threading
from threading import current_thread
import weakref

class _CallbackStorage:
  def __init__(self):
    self.storage = {}

  def add_new_callback(self, f):
    key = _get_request_id()
    if key in self.storage:
      self.storage[key].append(f)
    else:
      self.storage[key] = [f]

  def callback_by_request(self):
    key = _get_request_id()
    if key in self.storage:
      for callback in self.storage[key]:
        callback()

_callback_storage = _CallbackStorage()

def SetRequestEndCallback(callback):
  _callback_storage.add_new_callback(callback)


def _get_request_id():
  """Returns unique ID using the cloud trace id"""

  # TODO(bryanmau): Find the right key for both vm: true and env:2
  # Some options include cloud_trace_context and request_id_hash

  KEY = 'X_REQ_ID'

  if KEY in os.environ:
    req_id = os.environ[KEY]
  else:
    req_id = 'No Request ID'

  return req_id


class RequestLocal(object):

  def __new__(cls, *args, **kw):
    self = object.__new__(cls)
    object.__setattr__(self, '__storage__', {})

    if args or kw:
      raise TypeError("Initialization arguments are not supported")

    # This prevents __init__ from being called twice
    # In python if __new__ returns an instance that instance's
    # __init__ method is automatically called
    storage = object.__getattribute__(self, '__storage__')
    storage[_get_request_id()] = dict()

    return self

  def _initialize(self):
    req_id = _get_request_id()
    if req_id not in self.__storage__:
      self.__storage__[req_id] = dict()
      SetRequestEndCallback(self._cleanup)
      self.__init__()
    return req_id

  def __getattr__(self, name):
    req_id = self._initialize()

    try:
      return self.__storage__[req_id][name]
    except KeyError:
      raise AttributeError(name)

  def __setattr__(self, name, value):
    req_id = self._initialize()
    self.__storage__[req_id][name] = value

  def __delattr__(self, name):
    req_id = self._initialize()
    try:
      del self.__storage__[req_id][name]
    except KeyError:
      raise AttributeError(name)

  def _cleanup(self):
    req_id = _get_request_id()
    # NOTE(bryanmau): This if check is superfluous.  This function should
    # only be called if __setattr__ was called at some point, creating the
    # dictionary entry keyed by the request id.
    if req_id in self.__storage__:
      if self.__storage__[req_id]:
        k, v = self.__storage__[req_id].popitem()
      del self.__storage__[req_id]

