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

import xcatutils

from oslo.config import cfg
from neutron.openstack.common import log as logging
from neutron.openstack.common.gettextutils import _
from neutron.plugins.zvm.common import exception

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class zvmUtils(object):
    _MAX_REGRANT_USER_NUMBER = 1000

    def __init__(self):
        self._xcat_url = xcatutils.xCatURL()
        self._zhcp_userid = None
        self._userid_map = {}
        self._xcat_node_name = self._get_xcat_node_name()

    def get_node_from_port(self, port_id):
        return self._get_nic_settings(port_id, get_node=True)

    def get_nic_ids(self):
        addp = ''
        url = self._xcat_url.tabdump("/switch", addp)
        nic_settings = xcatutils.xcat_request("GET", url)
        # remove table header
        nic_settings['data'][0].pop(0)
        # it's possible to return empty array
        return nic_settings['data'][0]

    def _get_nic_settings(self, port_id, field=None, get_node=False):
        """Get NIC information from xCat switch table."""
        LOG.debug(_("Get nic information for port: %s"), port_id)
        addp = '&col=port&value=%s' % port_id + '&attribute=%s' % (
                                                field and field or 'node')
        url = self._xcat_url.gettab("/switch", addp)
        nic_settings = xcatutils.xcat_request("GET", url)
        ret_value = nic_settings['data'][0][0]
        if field is None and not get_node:
            ret_value = self.get_userid_from_node(ret_value)
        return ret_value

    def get_userid_from_node(self, node):
        addp = '&col=node&value=%s&attribute=userid' % node
        url = self._xcat_url.gettab("/zvm", addp)
        user_info = xcatutils.xcat_request("GET", url)
        return user_info['data'][0][0]

    def couple_nic_to_vswitch(self, vswitch_name, switch_port_name,
                                    zhcp, userid, dm=True, immdt=True):
        """Couple nic to vswitch."""
        LOG.debug(_("Connect nic to switch: %s"), vswitch_name)
        vdev = self._get_nic_settings(switch_port_name, "interface")
        if vdev:
            self._couple_nic(zhcp, vswitch_name, userid, vdev, dm, immdt)
        else:
            raise exception.zVMInvalidDataError(msg=('Cannot get vdev for '
                            'user %s, couple to port %s') %
                            (userid, switch_port_name))
        return vdev

    def uncouple_nic_from_vswitch(self, vswitch_name, switch_port_name,
                                    zhcp, userid, dm=True, immdt=True):
        """Uncouple nic from vswitch."""
        LOG.debug(_("Disconnect nic from switch: %s"), vswitch_name)
        vdev = self._get_nic_settings(switch_port_name, "interface")
        self._uncouple_nic(zhcp, userid, vdev, dm, immdt)

    def set_vswitch_port_vlan_id(self, vlan_id, switch_port_name, vdev, zhcp,
                                 vswitch_name):
        userid = self._get_nic_settings(switch_port_name)
        if not userid:
            raise exception.zVMInvalidDataError(msg=('Cannot get userid by '
                            'port %s') % (switch_port_name))
        url = self._xcat_url.xdsh("/%s" % zhcp)
        commands = '/opt/zhcp/bin/smcli Virtual_Network_Vswitch_Set_Extended'
        commands += " -T %s" % userid
        commands += ' -k grant_userid=%s' % userid
        commands += " -k switch_name=%s" % vswitch_name
        commands += " -k user_vlan_id=%s" % vlan_id
        xdsh_commands = 'command=%s' % commands
        body = [xdsh_commands]
        xcatutils.xcat_request("PUT", url, body)

    def grant_user(self, zhcp, vswitch_name, userid):
        """Set vswitch to grant user."""
        url = self._xcat_url.xdsh("/%s" % zhcp)
        commands = '/opt/zhcp/bin/smcli Virtual_Network_Vswitch_Set_Extended'
        commands += " -T %s" % userid
        commands += " -k switch_name=%s" % vswitch_name
        commands += " -k grant_userid=%s" % userid
        xdsh_commands = 'command=%s' % commands
        body = [xdsh_commands]
        xcatutils.xcat_request("PUT", url, body)

    def revoke_user(self, zhcp, vswitch_name, userid):
        """Set vswitch to grant user."""
        url = self._xcat_url.xdsh("/%s" % zhcp)
        commands = '/opt/zhcp/bin/smcli Virtual_Network_Vswitch_Set_Extended'
        commands += " -T %s" % userid
        commands += " -k switch_name=%s" % vswitch_name
        commands += " -k revoke_userid=%s" % userid
        xdsh_commands = 'command=%s' % commands
        body = [xdsh_commands]
        xcatutils.xcat_request("PUT", url, body)

    def _couple_nic(self, zhcp, vswitch_name, userid, vdev, dm, immdt):
        """Couple NIC to vswitch by adding vswitch into user direct."""
        url = self._xcat_url.xdsh("/%s" % zhcp)
        if dm:
            commands = '/opt/zhcp/bin/smcli'
            commands += ' Virtual_Network_Adapter_Connect_Vswitch_DM'
            commands += " -T %s " % userid + "-v %s" % vdev
            commands += " -n %s" % vswitch_name
            xdsh_commands = 'command=%s' % commands
            body = [xdsh_commands]
            xcatutils.xcat_request("PUT", url, body)
        if immdt:
            # the inst must be active, or this call will failed
            commands = '/opt/zhcp/bin/smcli'
            commands += ' Virtual_Network_Adapter_Connect_Vswitch'
            commands += " -T %s " % userid + "-v %s" % vdev
            commands += " -n %s" % vswitch_name
            xdsh_commands = 'command=%s' % commands
            body = [xdsh_commands]
            xcatutils.xcat_request("PUT", url, body)

    def _uncouple_nic(self, zhcp, userid, vdev, dm, immdt):
        """Couple NIC to vswitch by adding vswitch into user direct."""
        url = self._xcat_url.xdsh("/%s" % zhcp)
        if dm:
            commands = '/opt/zhcp/bin/smcli'
            commands += ' Virtual_Network_Adapter_Disconnect_DM'
            commands += " -T %s " % userid + "-v %s" % vdev
            xdsh_commands = 'command=%s' % commands
            body = [xdsh_commands]
            xcatutils.xcat_request("PUT", url, body)
        if immdt:
            # the inst must be active, or this call will failed
            commands = '/opt/zhcp/bin/smcli'
            commands += ' Virtual_Network_Adapter_Disconnect'
            commands += " -T %s " % userid + "-v %s" % vdev
            xdsh_commands = 'command=%s' % commands
            body = [xdsh_commands]
            xcatutils.xcat_request("PUT", url, body)

    def put_user_direct_online(self, zhcp, userid):
        url = self._xcat_url.xdsh("/%s" % zhcp)
        commands = '/opt/zhcp/bin/smcli Static_Image_Changes_Immediate_DM'
        commands += " -T %s" % userid
        xdsh_commands = 'command=%s' % commands
        body = [xdsh_commands]
        xcatutils.xcat_request("PUT", url, body)

    def get_zhcp_userid(self, zhcp):
        if not self._zhcp_userid:
            self._zhcp_userid = self.get_userid_from_node(zhcp)
        return self._zhcp_userid

    def add_vswitch(self, zhcp, name, rdev,
                    controller='*',
                    connection=1, queue_mem=8, router=0, network_type=2, vid=0,
                    port_type=1, update=1, gvrp=2, native_vid=1):
        '''
           connection:0-unspecified 1-Actice 2-non-Active
           router:0-unspecified 1-nonrouter 2-prirouter
           type:0-unspecified 1-IP 2-ethernet
           vid:1-4094 for access port defaut vlan
           port_type:0-unspecified 1-access 2-trunk
           update:0-unspecified 1-create 2-create and add to system
                  configuration file
           gvrp:0-unspecified 1-gvrp 2-nogvrp
        '''
        if (self._does_vswitch_exist(zhcp, name)):
            LOG.info(_('Vswitch %s already exists.'), name)
            return

        # if vid = 0, port_type, gvrp and native_vlanid are not
        # allowed to specified
        if not len(vid):
            vid = 0
            port_type = 0
            gvrp = 0
            native_vid = -1
        else:
            vid = str(vid[0][0]) + '-' + str(vid[0][1])

        userid = self.get_zhcp_userid(zhcp)
        url = self._xcat_url.xdsh("/%s" % zhcp)
        commands = '/opt/zhcp/bin/smcli Virtual_Network_Vswitch_Create'
        commands += " -T %s" % userid
        commands += ' -n %s' % name
        if rdev:
            commands += " -r %s" % rdev.replace(',', ' ')
        #commands += " -a %s" % osa_name
        if controller != '*':
            commands += " -i %s" % controller
        commands += " -c %s" % connection
        commands += " -q %s" % queue_mem
        commands += " -e %s" % router
        commands += " -t %s" % network_type
        commands += " -v %s" % vid
        commands += " -p %s" % port_type
        commands += " -u %s" % update
        commands += " -G %s" % gvrp
        commands += " -V %s" % native_vid
        xdsh_commands = 'command=%s' % commands
        body = [xdsh_commands]

        result = xcatutils.xcat_request("PUT", url, body)
        if (result['errorcode'][0][0] != '0') or \
            (not self._does_vswitch_exist(zhcp, name)):
            raise exception.zvmException(
                msg=("switch: %s add failed, %s") %
                        (name, result['data'][0][0]))
        LOG.info(_('Created vswitch %s done.'), name)

    def _does_vswitch_exist(self, zhcp, vsw):
        userid = self.get_zhcp_userid(zhcp)
        url = self._xcat_url.xdsh("/%s" % zhcp)
        commands = '/opt/zhcp/bin/smcli Virtual_Network_Vswitch_Query'
        commands += " -T %s" % userid
        commands += " -s %s" % vsw
        xdsh_commands = 'command=%s' % commands
        body = [xdsh_commands]
        result = xcatutils.xcat_request("PUT", url, body)

        return (result['errorcode'][0][0] == '0')

    def re_grant_user(self, zhcp):
        """Grant user again after z/VM is re-IPLed"""
        ports_info = self._get_userid_vswitch_vlan_id_mapping(zhcp)
        records_num = 0
        cmd = ''

        def run_command(command):
            xdsh_commands = 'command=%s' % command
            body = [xdsh_commands]
            url = self._xcat_url.xdsh("/%s" % zhcp)
            xcatutils.xcat_request("PUT", url, body)

        for (port_id, port) in ports_info.items():
            if port['userid'] is None or port['vswitch'] is None:
                continue
            if len(port['userid']) == 0 or len(port['vswitch']) == 0:
                continue

            cmd += '/opt/zhcp/bin/smcli '
            cmd += 'Virtual_Network_Vswitch_Set_Extended '
            cmd += '-T %s ' % port['userid']
            cmd += '-k switch_name=%s ' % port['vswitch']
            cmd += '-k grant_userid=%s' % port['userid']
            try:
                if int(port['vlan_id']) in range(1, 4094):
                    cmd += ' -k user_vlan_id=%s\n' % port['vlan_id']
                else:
                    cmd += '\n'
            except ValueError:
                # just in case there are bad records of vlan info which
                # could be a string
                LOG.warn(_("Unknown vlan '%(vlan)s' for user %(user)s."),
                            {'vlan': port['vlan_id'], 'user': port['userid']})
                cmd += '\n'
                continue
            records_num += 1
            if records_num >= self._MAX_REGRANT_USER_NUMBER:
                try:
                    commands = 'echo -e "#!/bin/sh\n%s" > grant.sh' % cmd[:-1]
                    run_command(commands)
                    commands = 'sh grant.sh;rm -f grant.sh'
                    run_command(commands)
                    records_num = 0
                    cmd = ''
                except Exception:
                    LOG.warn(_("Grant user failed"))

        if len(cmd) > 0:
            commands = 'echo -e "#!/bin/sh\n%s" > grant.sh' % cmd[:-1]
            run_command(commands)
            commands = 'sh grant.sh;rm -f grant.sh'
            run_command(commands)
        return ports_info

    def _get_userid_vswitch_vlan_id_mapping(self, zhcp):
        ports_info = self.get_nic_ids()
        ports = {}
        for p in ports_info:
            port_info = p.split(',')
            target_host = port_info[5].strip('"')
            port_vid = port_info[3].strip('"')
            port_id = port_info[2].strip('"')
            vswitch = port_info[1].strip('"')
            nodename = port_info[0].strip('"')
            if target_host == zhcp:
                ports[port_id] = {'nodename': nodename,
                                  'vswitch': vswitch,
                                  'userid': None,
                                  'vlan_id': port_vid}

        def get_all_userid():
            users = {}
            addp = ''
            url = self._xcat_url.tabdump("/zvm", addp)
            all_userids = xcatutils.xcat_request("GET", url)
            header = '#node,hcp,userid,nodetype,parent,comments,disable'
            all_userids['data'][0].remove(header)
            if len(all_userids) > 0:
                for u in all_userids['data'][0]:
                    user_info = u.split(',')
                    userid = user_info[2].strip('"')
                    nodename = user_info[0].strip('"')
                    users[nodename] = {'userid': userid}

            return users

        users = get_all_userid()

        for (port_id, port) in ports.items():
            try:
                ports[port_id]['userid'] = users[port['nodename']]['userid']
            except Exception:
                LOG.info(_("Garbage port found. port id: %s") % port_id)

        return ports

    def update_xcat_switch(self, port, vswitch, vlan):
        """Update information in xCAT switch table."""
        commands = "port=%s" % port
        commands += " switch.switch=%s" % vswitch
        commands += " switch.vlan=%s" % (vlan and vlan or -1)
        url = self._xcat_url.tabch("/switch")
        body = [commands]
        xcatutils.xcat_request("PUT", url, body)

    def create_xcat_mgt_network(self, zhcp, mgt_ip, mgt_mask, mgt_vswitch):
        url = self._xcat_url.xdsh("/%s" % zhcp)
        xdsh_commands = ('command=smcli Virtual_Network_Adapter_Query'
                  ' -T %s -v 0800') % self._xcat_node_name
        body = [xdsh_commands]
        result = xcatutils.xcat_request("PUT", url, body)['data'][0][0]
        code = result.split("\n")
        # return code 212: Adapter does not exist
        new_nic = ''
        if len(code) == 4 and code[1].split(': ')[2] == '212':
            new_nic = ('vmcp define nic 0800 type qdio\n' +
                    'vmcp couple 0800 system %s\n' % (mgt_vswitch))
        elif len(code) == 7:
            status = code[4].split(': ')[2]
            if status == 'Coupled and active':
                # we just assign the IP/mask,
                # no matter if it is assigned or not
                LOG.info(_("Assign IP for NIC 800."))
            else:
                LOG.error(_("NIC 800 staus is unknown."))
                return
        else:
            raise exception.zvmException(
                    msg="Unknown information from SMAPI")

        url = self._xcat_url.xdsh("/%s") % self._xcat_node_name
        cmd = new_nic + ('/usr/bin/perl /usr/sbin/sspqeth2.pl ' +
              '-a %s -d 0800 0801 0802 -e eth2 -m %s -g %s'
              % (mgt_ip, mgt_mask, mgt_ip))
        xdsh_commands = 'command=%s' % cmd
        body = [xdsh_commands]
        xcatutils.xcat_request("PUT", url, body)

    def _get_xcat_node_ip(self):
        addp = '&col=key&value=master&attribute=value'
        url = self._xcat_url.gettab("/site", addp)
        return xcatutils.xcat_request("GET", url)['data'][0][0]

    def _get_xcat_node_name(self):
        xcat_ip = self._get_xcat_node_ip()
        addp = '&col=ip&value=%s&attribute=node' % (xcat_ip)
        url = self._xcat_url.gettab("/hosts", addp)
        return (xcatutils.xcat_request("GET", url)['data'][0][0])

    def query_xcat_uptime(self, zhcp):
        url = self._xcat_url.xdsh("/%s" % zhcp)
        cmd = '/opt/zhcp/bin/smcli Image_Query_Activate_Time'
        cmd += " -T %s" % self.get_userid_from_node(
                                self._xcat_node_name)
        # format 4: yyyy-mm-dd
        cmd += " -f %s" % "4"
        xdsh_commands = 'command=%s' % cmd
        body = [xdsh_commands]
        ret_str = xcatutils.xcat_request("PUT", url, body)['data'][0][0]
        return ret_str.split('on ')[1]

    def query_zvm_uptime(self, zhcp):
        url = self._xcat_url.xdsh("/%s" % zhcp)
        cmd = '/opt/zhcp/bin/smcli System_Info_Query'
        xdsh_commands = 'command=%s' % cmd
        body = [xdsh_commands]
        ret_str = xcatutils.xcat_request("PUT", url, body)['data'][0][0]
        return ret_str.split('\n')[4].split(': ', 3)[2]
