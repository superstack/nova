# Copyright 2011 OpenStack LLC.
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

import common

from nova import exception
from nova import flags
from nova import log as logging
from nova import wsgi

from nova.auth import manager

FLAGS = flags.FLAGS
LOG = logging.getLogger('nova.api.openstack')


def _translate_keys(user):
    return dict(id=user.id,
                name=user.name,
                access=user.access,
                secret=user.secret,
                admin=user.admin)


class Controller(wsgi.Controller):

    _serialization_metadata = {
        'application/xml': {
            "attributes": {
                "user": ["id", "name", "access", "secret", "admin"]}}}

    def __init__(self):
        self.manager = manager.AuthManager()

    def _check_admin(self, context):
        """We cannot depend on the db layer to check for admin access
           for the auth manager, so we do it here"""
        if not context.is_admin:
            raise exception.NotAuthorized(_("Not admin user"))

    def index(self, req):
        """Return all users in brief"""
        users = self.manager.get_users()
        users = common.limited(users, req)
        users = [_translate_keys(user) for user in users]
        return dict(users=users)

    def detail(self, req):
        """Return all users in detail"""
        return self.index(req)

    def show(self, req, id):
        """Return data about the given user id"""
        user = self.manager.get_user(id)
        return dict(user=_translate_keys(user))

    def delete(self, req, id):
        self._check_admin(req.environ['nova.context'])
        self.manager.delete_user(id)
        return {}

    def create(self, req):
        self._check_admin(req.environ['nova.context'])
        env = self._deserialize(req.body, req.get_content_type())
        is_admin = env['user'].get('admin') in ('T', 'True', True)
        name = env['user'].get('name')
        access = env['user'].get('access')
        secret = env['user'].get('secret')
        user = self.manager.create_user(name, access, secret, is_admin)
        return dict(user=_translate_keys(user))

    def update(self, req, id):
        self._check_admin(req.environ['nova.context'])
        env = self._deserialize(req.body, req.get_content_type())
        is_admin = env['user'].get('admin')
        if is_admin is not None:
            is_admin = is_admin in ('T', 'True', True)
        access = env['user'].get('access')
        secret = env['user'].get('secret')
        self.manager.modify_user(id, access, secret, is_admin)
        return dict(user=_translate_keys(self.manager.get_user(id)))
