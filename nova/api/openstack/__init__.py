# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

"""
WSGI middleware for OpenStack API controllers.
"""

import routes
import webob.dec
import webob.exc

from nova import flags
from nova import log as logging
from nova import wsgi
from nova.api.openstack import accounts
from nova.api.openstack import faults
from nova.api.openstack import backup_schedules
from nova.api.openstack import consoles
from nova.api.openstack import flavors
from nova.api.openstack import images
from nova.api.openstack import image_metadata
from nova.api.openstack import ips
from nova.api.openstack import limits
from nova.api.openstack import servers
from nova.api.openstack import server_metadata
from nova.api.openstack import shared_ip_groups
from nova.api.openstack import users
from nova.api.openstack import zones


LOG = logging.getLogger('nova.api.openstack')
FLAGS = flags.FLAGS
flags.DEFINE_bool('allow_admin_api',
    False,
    'When True, this API service will accept admin operations.')


class FaultWrapper(wsgi.Middleware):
    """Calls down the middleware stack, making exceptions into faults."""

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        try:
            return req.get_response(self.application)
        except Exception as ex:
            LOG.exception(_("Caught error: %s"), unicode(ex))
            exc = webob.exc.HTTPInternalServerError(explanation=unicode(ex))
            return faults.Fault(exc)


class APIRouter(wsgi.Router):
    """
    Routes requests on the OpenStack API to the appropriate controller
    and method.
    """

    @classmethod
    def factory(cls, global_config, **local_config):
        """Simple paste factory, :class:`nova.wsgi.Router` doesn't have one"""
        return cls()

    def __init__(self, ext_mgr=None):
        self.server_members = {}
        mapper = routes.Mapper()
        self._setup_routes(mapper)
        super(APIRouter, self).__init__(mapper)

    def _setup_routes(self, mapper):
        server_members = self.server_members
        server_members['action'] = 'POST'
        if FLAGS.allow_admin_api:
            LOG.debug(_("Including admin operations in API."))

            server_members['pause'] = 'POST'
            server_members['unpause'] = 'POST'
            server_members['diagnostics'] = 'GET'
            server_members['actions'] = 'GET'
            server_members['suspend'] = 'POST'
            server_members['resume'] = 'POST'
            server_members['rescue'] = 'POST'
            server_members['unrescue'] = 'POST'
            server_members['reset_network'] = 'POST'
            server_members['inject_network_info'] = 'POST'

            mapper.resource("zone", "zones", controller=zones.Controller(),
                        collection={'detail': 'GET', 'info': 'GET',
                                    'select': 'GET'})

            mapper.resource("user", "users", controller=users.Controller(),
                        collection={'detail': 'GET'})

            mapper.resource("account", "accounts",
                            controller=accounts.Controller(),
                            collection={'detail': 'GET'})

        mapper.resource("console", "consoles",
                        controller=consoles.Controller(),
                        parent_resource=dict(member_name='server',
                        collection_name='servers'))

        super(APIRouter, self).__init__(mapper)


class APIRouterV10(APIRouter):
    """Define routes specific to OpenStack API V1.0."""

    def _setup_routes(self, mapper):
        super(APIRouterV10, self)._setup_routes(mapper)
        mapper.resource("server", "servers",
                        controller=servers.ControllerV10(),
                        collection={'detail': 'GET'},
                        member=self.server_members)

        mapper.resource("image", "images",
                        controller=images.ControllerV10(),
                        collection={'detail': 'GET'})

        mapper.resource("flavor", "flavors",
                        controller=flavors.ControllerV10(),
                        collection={'detail': 'GET'})

        mapper.resource("shared_ip_group", "shared_ip_groups",
                        collection={'detail': 'GET'},
                        controller=shared_ip_groups.Controller())

        mapper.resource("backup_schedule", "backup_schedule",
                        controller=backup_schedules.Controller(),
                        parent_resource=dict(member_name='server',
                        collection_name='servers'))

        mapper.resource("limit", "limits",
                        controller=limits.LimitsControllerV10())

        mapper.resource("ip", "ips", controller=ips.Controller(),
                        collection=dict(public='GET', private='GET'),
                        parent_resource=dict(member_name='server',
                                             collection_name='servers'))


class APIRouterV11(APIRouter):
    """Define routes specific to OpenStack API V1.1."""

    def _setup_routes(self, mapper):
        super(APIRouterV11, self)._setup_routes(mapper)
        mapper.resource("server", "servers",
                        controller=servers.ControllerV11(),
                        collection={'detail': 'GET'},
                        member=self.server_members)

        mapper.resource("image", "images",
                        controller=images.ControllerV11(),
                        collection={'detail': 'GET'})

        mapper.resource("image_meta", "meta",
                        controller=image_metadata.Controller(),
                        parent_resource=dict(member_name='image',
                        collection_name='images'))

        mapper.resource("server_meta", "meta",
                        controller=server_metadata.Controller(),
                        parent_resource=dict(member_name='server',
                        collection_name='servers'))

        mapper.resource("flavor", "flavors",
                        controller=flavors.ControllerV11(),
                        collection={'detail': 'GET'})

        mapper.resource("limit", "limits",
                        controller=limits.LimitsControllerV11())
