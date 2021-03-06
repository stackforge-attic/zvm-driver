# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2014 IBM Corp.
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
Unit tests for the z/VM xCAT utils.
"""

import mock

from oslo.config import cfg
from neutron.plugins.zvm.common import xcatutils
from neutron.tests import base


class TestZVMXcatUtils(base.BaseTestCase):
    _FAKE_XCAT_SERVER = "127.0.0.1"
    _FAKE_XCAT_TIMEOUT = 300

    def setUp(self):
        super(TestZVMXcatUtils, self).setUp()
        cfg.CONF.set_override('zvm_xcat_server',
                              self._FAKE_XCAT_SERVER, 'AGENT')
        cfg.CONF.set_override('zvm_xcat_timeout',
                              self._FAKE_XCAT_TIMEOUT, 'AGENT')
        self._xcaturl = xcatutils.xCatURL()
        with mock.patch.multiple(xcatutils.httplib,
            HTTPSConnection=mock.MagicMock()):
            self._zvm_xcat_connection = xcatutils.xCatConnection()
