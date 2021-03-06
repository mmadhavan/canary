# Copyright (c) 2015 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Redis backend driver implementation."""

from oslo_config import cfg
import redis
from redis import exceptions as redis_exceptions
import six
import time
import json
from canary.openstack.common import log as logging
from canary.util import canonicalize
import base64

conf = cfg.CONF
conf(project='canary', prog='canary', args=[])
logging.setup('canary')


LOG = logging.getLogger(__name__)


_REDIS_OPTIONS = [
    cfg.ListOpt('cluster', default=['127.0.0.1'],
        help='Redis cluster contact points'),
    cfg.IntOpt('port', default=6379, 
               help='Redis cluster port'),
    cfg.IntOpt('db', default=4, 
               help='default db to use in redis cluster')
]

REDIS_GROUP = cfg.OptGroup(
        name='redis',
        title='redis options'
    )

conf.register_opts(_REDIS_OPTIONS, group=REDIS_GROUP)

def _raise_on_closed(meth):

    @six.wraps(meth)
    def wrapper(self, *args, **kwargs):
        if self.closed:
            raise redis_exceptions.ConnectionError("Connection has been"
                                                   " closed")
        return meth(self, *args, **kwargs)

    return wrapper


class RedisClient(redis.StrictRedis):
    """A redis client that can be closed (and raises on-usage after closed).

    TODO(tonytan4ever): if https://github.com/andymccurdy/redis-py/issues/613 ever
    gets resolved or merged or other then we can likely remove this.
    """

    def __init__(self, *args, **kwargs):
        #super(RedisClient, self).__init__(*args, **kwargs)
        super(RedisClient, self).__init__(host='localhost', port=6379, db=4)
        self.closed = False

    def close(self):
        self.closed = True
        self.connection_pool.disconnect()

    zadd = _raise_on_closed(redis.StrictRedis.zadd)
    zrangebyscore = _raise_on_closed(redis.StrictRedis.zrangebyscore)

    #TODO: Cleanup these commands if they are not in use.
    '''
    execute_command = _raise_on_closed(redis.StrictRedis.execute_command)
    transaction = _raise_on_closed(redis.StrictRedis.transaction)
    pubsub = _raise_on_closed(redis.StrictRedis.pubsub)
    '''

def _connection(conf):
    client_conf = {}
    for key in conf.keys():
        client_conf[key] = conf[key]
    return RedisClient(client_conf)
    

class RedisStorageDriver(object):
    """Redis Storage Driver."""
      
    def __init__(self):
        super(RedisStorageDriver, self).__init__()
        self.session = _connection(conf)
        self.create_session()

    def create_session(self):
        return self.session

    def insert_job_details(self,path,job_count,job_details):
        encoded_data = base64.b64encode(json.dumps({'path': path,'jobs':job_details,'job_count':job_count}))
        self.session.zadd('canary:info',time.time(),encoded_data)
    
    def set_last_read_time(self):
        self.session.set('canary:last_read',time.time())

    def get_job_details(self):
        result = []
        if not self.session.keys('canary:last_read'):
            res = self.session.zrangebyscore('canary:info',0.0, time.time())
            self.set_last_read_time()
        else:
            res = self.session.zrangebyscore('canary:info',time.time() - float(self.session.get('canary:last_read')), time.time())
            self.set_last_read_time()
        return res 
