# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import datetime
import json

import stubout
import webob

from nova import db
from nova import flags
from nova import test
import nova.api.openstack
from nova.api.openstack import servers
import nova.compute.api
import nova.db.api
from nova.db.sqlalchemy.models import Instance
from nova.db.sqlalchemy.models import InstanceMetadata
import nova.rpc
from nova.tests.api.openstack import common
from nova.tests.api.openstack import fakes


FLAGS = flags.FLAGS
FLAGS.verbose = True


def return_server(context, id):
    return stub_instance(id)


def return_server_with_addresses(private, public):
    def _return_server(context, id):
        return stub_instance(id, private_address=private,
                             public_addresses=public)
    return _return_server


def return_servers(context, user_id=1):
    return [stub_instance(i, user_id) for i in xrange(5)]


def return_security_group(context, instance_id, security_group_id):
    pass


def instance_update(context, instance_id, kwargs):
    return stub_instance(instance_id)


def instance_address(context, instance_id):
    return None


def stub_instance(id, user_id=1, private_address=None, public_addresses=None):
    metadata = []
    metadata.append(InstanceMetadata(key='seq', value=id))

    if public_addresses == None:
        public_addresses = list()

    instance = {
        "id": id,
        "admin_pass": "",
        "user_id": user_id,
        "project_id": "",
        "image_id": 10,
        "kernel_id": "",
        "ramdisk_id": "",
        "launch_index": 0,
        "key_name": "",
        "key_data": "",
        "state": 0,
        "state_description": "",
        "memory_mb": 0,
        "vcpus": 0,
        "local_gb": 0,
        "hostname": "",
        "host": None,
        "instance_type": "",
        "user_data": "",
        "reservation_id": "",
        "mac_address": "",
        "scheduled_at": datetime.datetime.now(),
        "launched_at": datetime.datetime.now(),
        "terminated_at": datetime.datetime.now(),
        "availability_zone": "",
        "display_name": "server%s" % id,
        "display_description": "",
        "locked": False,
        "metadata": metadata}

    instance["fixed_ip"] = {
        "address": private_address,
        "floating_ips": [{"address":ip} for ip in public_addresses]}

    return instance


def fake_compute_api(cls, req, id):
    return True


class ServersTest(test.TestCase):

    def setUp(self):
        super(ServersTest, self).setUp()
        self.stubs = stubout.StubOutForTesting()
        fakes.FakeAuthManager.reset_fake_data()
        fakes.FakeAuthDatabase.data = {}
        fakes.stub_out_networking(self.stubs)
        fakes.stub_out_rate_limiting(self.stubs)
        fakes.stub_out_auth(self.stubs)
        fakes.stub_out_key_pair_funcs(self.stubs)
        fakes.stub_out_image_service(self.stubs)
        self.stubs.Set(nova.db.api, 'instance_get_all', return_servers)
        self.stubs.Set(nova.db.api, 'instance_get', return_server)
        self.stubs.Set(nova.db.api, 'instance_get_all_by_user',
                       return_servers)
        self.stubs.Set(nova.db.api, 'instance_add_security_group',
                       return_security_group)
        self.stubs.Set(nova.db.api, 'instance_update', instance_update)
        self.stubs.Set(nova.db.api, 'instance_get_fixed_address',
                       instance_address)
        self.stubs.Set(nova.db.api, 'instance_get_floating_address',
                       instance_address)
        self.stubs.Set(nova.compute.API, 'pause', fake_compute_api)
        self.stubs.Set(nova.compute.API, 'unpause', fake_compute_api)
        self.stubs.Set(nova.compute.API, 'suspend', fake_compute_api)
        self.stubs.Set(nova.compute.API, 'resume', fake_compute_api)
        self.stubs.Set(nova.compute.API, "get_diagnostics", fake_compute_api)
        self.stubs.Set(nova.compute.API, "get_actions", fake_compute_api)
        self.allow_admin = FLAGS.allow_admin_api

        self.webreq = common.webob_factory('/v1.0/servers')

    def tearDown(self):
        self.stubs.UnsetAll()
        FLAGS.allow_admin_api = self.allow_admin
        super(ServersTest, self).tearDown()

    def test_get_server_by_id(self):
        req = webob.Request.blank('/v1.0/servers/1')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict['server']['id'], '1')
        self.assertEqual(res_dict['server']['name'], 'server1')

    def test_get_server_by_id_with_addresses(self):
        private = "192.168.0.3"
        public = ["1.2.3.4"]
        new_return_server = return_server_with_addresses(private, public)
        self.stubs.Set(nova.db.api, 'instance_get', new_return_server)
        req = webob.Request.blank('/v1.0/servers/1')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)
        self.assertEqual(res_dict['server']['id'], '1')
        self.assertEqual(res_dict['server']['name'], 'server1')
        addresses = res_dict['server']['addresses']
        self.assertEqual(len(addresses["public"]), len(public))
        self.assertEqual(addresses["public"][0], public[0])
        self.assertEqual(len(addresses["private"]), 1)
        self.assertEqual(addresses["private"][0], private)

    def test_get_server_list(self):
        req = webob.Request.blank('/v1.0/servers')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        i = 0
        for s in res_dict['servers']:
            self.assertEqual(s['id'], i)
            self.assertEqual(s['name'], 'server%d' % i)
            self.assertEqual(s.get('imageId', None), None)
            i += 1

    def test_get_servers_with_limit(self):
        req = webob.Request.blank('/v1.0/servers?limit=3')
        res = req.get_response(fakes.wsgi_app())
        servers = json.loads(res.body)['servers']
        self.assertEqual([s['id'] for s in servers], [0, 1, 2])

        req = webob.Request.blank('/v1.0/servers?limit=aaa')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)
        self.assertTrue('limit' in res.body)

    def test_get_servers_with_offset(self):
        req = webob.Request.blank('/v1.0/servers?offset=2')
        res = req.get_response(fakes.wsgi_app())
        servers = json.loads(res.body)['servers']
        self.assertEqual([s['id'] for s in servers], [2, 3, 4])

        req = webob.Request.blank('/v1.0/servers?offset=aaa')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)
        self.assertTrue('offset' in res.body)

    def test_get_servers_with_limit_and_offset(self):
        req = webob.Request.blank('/v1.0/servers?limit=2&offset=1')
        res = req.get_response(fakes.wsgi_app())
        servers = json.loads(res.body)['servers']
        self.assertEqual([s['id'] for s in servers], [1, 2])

    def test_create_instance(self):
        def instance_create(context, inst):
            return {'id': '1', 'display_name': 'server_test'}

        def server_update(context, id, params):
            return instance_create(context, id)

        def fake_method(*args, **kwargs):
            pass

        def project_get_network(context, user_id):
            return dict(id='1', host='localhost')

        def queue_get_for(context, *args):
            return 'network_topic'

        def kernel_ramdisk_mapping(*args, **kwargs):
            return (1, 1)

        def image_id_from_hash(*args, **kwargs):
            return 2

        self.stubs.Set(nova.db.api, 'project_get_network', project_get_network)
        self.stubs.Set(nova.db.api, 'instance_create', instance_create)
        self.stubs.Set(nova.rpc, 'cast', fake_method)
        self.stubs.Set(nova.rpc, 'call', fake_method)
        self.stubs.Set(nova.db.api, 'instance_update',
            server_update)
        self.stubs.Set(nova.db.api, 'queue_get_for', queue_get_for)
        self.stubs.Set(nova.network.manager.VlanManager, 'allocate_fixed_ip',
            fake_method)
        self.stubs.Set(nova.api.openstack.servers.Controller,
            "_get_kernel_ramdisk_from_image", kernel_ramdisk_mapping)
        self.stubs.Set(nova.api.openstack.common,
            "get_image_id_from_image_hash", image_id_from_hash)

        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2,
            metadata={'hello': 'world', 'open': 'stack'},
            personality={}))
        req = webob.Request.blank('/v1.0/servers')
        req.method = 'POST'
        req.body = json.dumps(body)
        req.headers["Content-Type"] = "application/json"

        res = req.get_response(fakes.wsgi_app())

        server = json.loads(res.body)['server']
        self.assertEqual('serv', server['adminPass'][:4])
        self.assertEqual(16, len(server['adminPass']))
        self.assertEqual('server_test', server['name'])
        self.assertEqual('1', server['id'])

        self.assertEqual(res.status_int, 200)

    def test_update_no_body(self):
        req = webob.Request.blank('/v1.0/servers/1')
        req.method = 'PUT'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 422)

    def test_update_bad_params(self):
        """ Confirm that update is filtering params """
        inst_dict = dict(cat='leopard', name='server_test', adminPass='bacon')
        self.body = json.dumps(dict(server=inst_dict))

        def server_update(context, id, params):
            self.update_called = True
            filtered_dict = dict(name='server_test', admin_pass='bacon')
            self.assertEqual(params, filtered_dict)

        self.stubs.Set(nova.db.api, 'instance_update',
            server_update)

        req = webob.Request.blank('/v1.0/servers/1')
        req.method = 'PUT'
        req.body = self.body
        req.get_response(fakes.wsgi_app())

    def test_update_server(self):
        inst_dict = dict(name='server_test', adminPass='bacon')
        self.body = json.dumps(dict(server=inst_dict))

        def server_update(context, id, params):
            filtered_dict = dict(name='server_test', admin_pass='bacon')
            self.assertEqual(params, filtered_dict)

        self.stubs.Set(nova.db.api, 'instance_update',
            server_update)

        req = webob.Request.blank('/v1.0/servers/1')
        req.method = 'PUT'
        req.body = self.body
        req.get_response(fakes.wsgi_app())

    def test_create_backup_schedules(self):
        req = webob.Request.blank('/v1.0/servers/1/backup_schedules')
        req.method = 'POST'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status, '404 Not Found')

    def test_delete_backup_schedules(self):
        req = webob.Request.blank('/v1.0/servers/1/backup_schedules')
        req.method = 'DELETE'
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status, '404 Not Found')

    def test_get_server_backup_schedules(self):
        req = webob.Request.blank('/v1.0/servers/1/backup_schedules')
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status, '404 Not Found')

    def test_get_all_server_details(self):
        req = webob.Request.blank('/v1.0/servers/detail')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        i = 0
        for s in res_dict['servers']:
            self.assertEqual(s['id'], i)
            self.assertEqual(s['hostId'], '')
            self.assertEqual(s['name'], 'server%d' % i)
            self.assertEqual(s['imageId'], 10)
            self.assertEqual(s['metadata']['seq'], i)
            i += 1

    def test_get_all_server_details_with_host(self):
        '''
        We want to make sure that if two instances are on the same host, then
        they return the same hostId. If two instances are on different hosts,
        they should return different hostId's. In this test, there are 5
        instances - 2 on one host and 3 on another.
        '''

        def stub_instance(id, user_id=1):
            return Instance(id=id, state=0, image_id=10, user_id=user_id,
                display_name='server%s' % id, host='host%s' % (id % 2))

        def return_servers_with_host(context, user_id=1):
            return [stub_instance(i) for i in xrange(5)]

        self.stubs.Set(nova.db.api, 'instance_get_all_by_user',
            return_servers_with_host)

        req = webob.Request.blank('/v1.0/servers/detail')
        res = req.get_response(fakes.wsgi_app())
        res_dict = json.loads(res.body)

        server_list = res_dict['servers']
        host_ids = [server_list[0]['hostId'], server_list[1]['hostId']]
        self.assertTrue(host_ids[0] and host_ids[1])
        self.assertNotEqual(host_ids[0], host_ids[1])

        for i, s in enumerate(res_dict['servers']):
            self.assertEqual(s['id'], i)
            self.assertEqual(s['hostId'], host_ids[i % 2])
            self.assertEqual(s['name'], 'server%d' % i)
            self.assertEqual(s['imageId'], 10)

    def test_server_pause(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/pause')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_unpause(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/unpause')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_suspend(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/suspend')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_resume(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/resume')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_reset_network(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/reset_network')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_inject_network_info(self):
        FLAGS.allow_admin_api = True
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank(
              '/v1.0/servers/1/inject_network_info')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)

    def test_server_diagnostics(self):
        req = webob.Request.blank("/v1.0/servers/1/diagnostics")
        req.method = "GET"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_server_actions(self):
        req = webob.Request.blank("/v1.0/servers/1/actions")
        req.method = "GET"
        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 404)

    def test_server_reboot(self):
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())

    def test_server_rebuild(self):
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())

    def test_server_resize(self):
        body = dict(server=dict(
            name='server_test', imageId=2, flavorId=2, metadata={},
            personality={}))
        req = webob.Request.blank('/v1.0/servers/1/action')
        req.method = 'POST'
        req.content_type = 'application/json'
        req.body = json.dumps(body)
        res = req.get_response(fakes.wsgi_app())

    def test_delete_server_instance(self):
        req = webob.Request.blank('/v1.0/servers/1')
        req.method = 'DELETE'

        self.server_delete_called = False

        def instance_destroy_mock(context, id):
            self.server_delete_called = True

        self.stubs.Set(nova.db.api, 'instance_destroy',
            instance_destroy_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status, '202 Accepted')
        self.assertEqual(self.server_delete_called, True)

    def test_resize_server(self):
        req = self.webreq('/1/action', 'POST', dict(resize=dict(flavorId=3)))

        self.resize_called = False

        def resize_mock(*args):
            self.resize_called = True

        self.stubs.Set(nova.compute.api.API, 'resize', resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)
        self.assertEqual(self.resize_called, True)

    def test_resize_bad_flavor_fails(self):
        req = self.webreq('/1/action', 'POST', dict(resize=dict(derp=3)))

        self.resize_called = False

        def resize_mock(*args):
            self.resize_called = True

        self.stubs.Set(nova.compute.api.API, 'resize', resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 422)
        self.assertEqual(self.resize_called, False)

    def test_resize_raises_fails(self):
        req = self.webreq('/1/action', 'POST', dict(resize=dict(flavorId=3)))

        def resize_mock(*args):
            raise Exception('hurr durr')

        self.stubs.Set(nova.compute.api.API, 'resize', resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_confirm_resize_server(self):
        req = self.webreq('/1/action', 'POST', dict(confirmResize=None))

        self.resize_called = False

        def confirm_resize_mock(*args):
            self.resize_called = True

        self.stubs.Set(nova.compute.api.API, 'confirm_resize',
                confirm_resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 204)
        self.assertEqual(self.resize_called, True)

    def test_confirm_resize_server_fails(self):
        req = self.webreq('/1/action', 'POST', dict(confirmResize=None))

        def confirm_resize_mock(*args):
            raise Exception('hurr durr')

        self.stubs.Set(nova.compute.api.API, 'confirm_resize',
                confirm_resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

    def test_revert_resize_server(self):
        req = self.webreq('/1/action', 'POST', dict(revertResize=None))

        self.resize_called = False

        def revert_resize_mock(*args):
            self.resize_called = True

        self.stubs.Set(nova.compute.api.API, 'revert_resize',
                revert_resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 202)
        self.assertEqual(self.resize_called, True)

    def test_revert_resize_server_fails(self):
        req = self.webreq('/1/action', 'POST', dict(revertResize=None))

        def revert_resize_mock(*args):
            raise Exception('hurr durr')

        self.stubs.Set(nova.compute.api.API, 'revert_resize',
                revert_resize_mock)

        res = req.get_response(fakes.wsgi_app())
        self.assertEqual(res.status_int, 400)

if __name__ == "__main__":
    unittest.main()
