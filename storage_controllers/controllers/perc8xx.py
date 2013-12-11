# Copyright (c) 2013 Daniele Valeriani (daniele@dvaleriani.net).
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

# Collection of functions and classes to interact with the the Perc 8xx
# controllers found in Dell servers and others.

import xml.etree.ElementTree as ET
import os
import subprocess
from storage_controllers.common import exceptions



def _check_initialised(func):
    def check_id(self, *args, **kwargs):
        if hasattr(self, 'id'):
            return func(self, *args, **kwargs)
        else:
            raise exceptions.ControllerError('Not initialised')
    return check_id


def run(cmd, args):
    commands = ['omconfig', 'omreport']
    basepath = "/opt/dell/srvadmin/bin"
    binaries = {x: os.path.join(basepath, x) for x in commands}
    for f in binaries.values():
        if not os.access(f, os.X_OK):
            raise OSError(os.errno.ENOEXEC)
    cmd = [binaries[cmd]]
    cmd.extend(args.split(' '))
    cmd.extend(['-fmt', 'xml'])
    output = subprocess.Popen(cmd, stdout=subprocess.PIPE).communicate()[0]
    if "Error! User has insufficient privileges to run command." in output:
        raise exceptions.ControllerError("Not enough privileges to perform "
                                         "this operation. Are you root?")
    return ET.fromstring(output.strip())


def get_controllers():
    """
    Returns a list of perc controllers instances for this server

    :param controller_id: The id of the requested controller.
    """
    res = run('omreport', 'storage controller')
    if res.find('Controllers') is None:
        raise exceptions.ControllerError("Unable to retrieve "
                                         "controller information")
    controllers = res.find('Controllers')
    ids = [controller.find('ControllerNum').text for controller in controllers]
    return [Controller(x) for x in ids]


def get_logical_drive(name):
    """
    Returns a logical drive instance given the name.

    :param name: The logical drive name. Es: c2u35.
    :returns: A LogicalDrive instance for that name.
    """
    controller_id, logical_drive_id = name.strip('c').split('u')
    return LogicalDrive(controller_id, logical_drive_id)


def get_physical_drive(controller_id, physical_drive_id):
    """
    Returns a physical drive instance given the coordinates.

    :param controller_id: The controller where this physical drive is attached to.
    :param physical_drive_id: The id of the physical drive.
    :returns: A PhysicalDrive instance.
    """
    return PhysicalDrive(controller_id, physical_drive_id)


def _check_exit_code(result, error):
    '''
    Check the exit code from the xml output of an omconfig command

    :param result: The xml output
    :param error: The error to return in case something went wrong
    '''
    if (not len(result.findall('CustomStat')) or
            result.find('CustomStat').text != '0'):
        raise exceptions.ControllerError(error)


def _parse_logical_drive(xml_input, logical_drive):
    """
    Parse the xml returned by the omreport command and assign attributes to
    a logical drive object.

    :param xml_input: The xml to parse.
    :param logical_drive: The logical drive object to act on.
    """
    logical_drive.id = xml_input.find('LogicalDriveNum').text
    logical_drive.device_path = xml_input.find('DeviceName').text

    status_mapping = {
        '2': "Online",
        '4': "Failed"
    }
    logical_drive.status = status_mapping[xml_input.find('ObjStatus').text]

    raid_mapping = {
        '2': "RAID-0",
        '4': "RAID-1"
    }
    logical_drive.type = raid_mapping[xml_input.find('Layout').text]

    return logical_drive


def _parse_physical_drive(xml_input, physical_drive):
    """
    Parse the xml returned by the omreport command and assign attributes to
    a physical drive object.

    :param xml_input: The xml to parse.
    :param physical_drive: The physical drive object to act on.
    """
    physical_drive.id = '{0}:0:{1}'.format(xml_input.find('Channel').text,
                        xml_input.find('TargetID').text)
    physical_drive.firmware = xml_input.find('Revision').text
    # For some reason the perc controller reports size in decimal, not binary
    physical_drive.size = int(xml_input.find('Length').text) / 1000000000000
    physical_drive.model = xml_input.find('ProductID').text
    physical_drive.serial = xml_input.find('DeviceSerialNumber').text

    state_mapping = {
        '1': "Ready",
        '2': "Failed",
        '4': "Online"
    }
    physical_drive.state = state_mapping[xml_input.find('ObjState').text]

    status_mapping = {
        '2': "Ok",  # Ok
        '3': "Non-Critical",  # Non-Critical
        '4': "Failed"
    }
    physical_drive.status = status_mapping[xml_input.find('ObjStatus').text]

    return physical_drive


class Controller():
    def __init__(self, controller_id):
        """
        Runs a single big command to fetch all the information for this controller.
        It's up to each method to digest its output.

        :param controller_id: The controller id
        """
        self.controller_id = controller_id
        res = run('omreport', 'storage controller controller={0}'.format(
                  self.controller_id))
        if res.find('Controllers') is None:
            raise exceptions.ControllerError("Unable to retrieve controller "
                                       "information for controller {0}".format(
                                       self.controller_id))
        self.controller_info = res.find('Controllers')[0]

    def get_info(self):
        '''
        Returns dict with: pci id, model, firmware, status
        '''
        return {
            'firmware': self.controller_info.find('FirmwareVer').text,
            'id': self.controller_id,
            'model': self.controller_info.find('Name').text,
            'pci_id': self.controller_info.find('PciID').text,
            'slot': self.controller_info.find('PCISlot').text
        }

    def get_logical_drives(self):
        '''
        Scan the controller and return a list of LogicalDrive instances.
        '''
        res = run('omreport', 'storage vdisk controller={0}'.format(self.controller_id))
        if res.find('VirtualDisks') is None:
            raise exceptions.ControllerError("Unable to retrieve logical drives "
                                       "information for controller {0}".format(
                                       self.controller_id))
        logical_drives = []
        for entry in res.find('VirtualDisks'):
            logical_drive = _parse_logical_drive(entry, LogicalDrive())
            logical_drive.controller_id = self.controller_id
            logical_drive.name = 'c{0}u{1}'.format(self.controller_id,
                                                   logical_drive.id)
            logical_drives.append(logical_drive)
        return logical_drives

    def get_physical_drives(self):
        '''
        Scan the controller and return a list of PhysicalDrive instances.
        '''
        res = run('omreport', 'storage pdisk controller={0}'.format(
                  self.controller_id))
        if res.find('ArrayDisks') is None:
            raise exceptions.ControllerError("Unable to retrieve physical drives "
                                       "information for controller {0}".format(
                                       self.controller_id))
        physical_drives = []
        for entry in res.find('ArrayDisks'):
            physical_drive = _parse_physical_drive(entry, PhysicalDrive())
            physical_drive.controller_id = self.controller_id
            physical_drives.append(physical_drive)
        return physical_drives

    def create_logical_drive(self, physical_drive):
        """
        Create a new logical drive.
        """
        # Get the list of vdisk ids currently configured on the controller.
        # This is horrible, but it's the only way I can get the vdisk id
        # after its creation. The omconfig command only returns the exit code,
        # nothing else, and there's no way to get the vdisk starting from the
        # pdisk. This is so prone to bugs.
        before_ids = [x.id for x in iter(self.get_logical_drives())]
        # Create the vdisk
        # TODO: Get the options line from the config, with specific options
        #       for each controller. Useful for multiple Perc controllers
        #       dealing with storage drives and OS drives.
        res = run('omconfig', 'storage controller controller={0} '
                  'action=createvdisk pdisk={1} raid=r0 size=max '
                  'stripesize=64kb diskcachepolicy=disabled readpolicy=ara '
                  'writepolicy=wb'''.format(self.controller_id, physical_drive))
        _check_exit_code(res, "Failed to create a logical drive on controller "
                         "{0} with physical drives {1}".format(
                         self.controller_id, physical_drive))
        # Now let's get the list again to find the new id.
        after_ids = [x.id for x in iter(self.get_logical_drives())]
        new_vdisk_ids = set(after_ids).difference(set(before_ids))
        if len(new_vdisk_ids) != 1:
            raise base.ControllerError('Problem after creating a vdisk for '
                                       'physical drives {0}: cannot compute '
                                       'the new vdisk id'.format(physical_drive))
        else:
            new_vdisk_id = new_vdisk_ids.pop()
        return LogicalDrive(self.controller_id, new_vdisk_id).get_info()


class LogicalDrive():
    def __init__(self, controller_id=None, vdisk_id=None):
        """
        None decides if the instance should be manually or automatically
        populated.

        :param controller_id: The controller id
        :param vdisk_id: The vdisk id
        """
        if (controller_id is not None and vdisk_id is not None):
            res = run('omreport', 'storage vdisk controller={0} vdisk={1}'.format(
                      controller_id, vdisk_id))
            if res.find('VirtualDisks') is None:
                raise exceptions.ControllerError("Unable to retrieve information for "
                                           "logical drive {0} on controller "
                                           "{1}".format(vdisk_id,
                                           controller_id))
            entry = res.find('VirtualDisks')[0]
            self = _parse_logical_drive(entry, self)
            self.controller_id = controller_id
            self.id = vdisk_id
            self.name = 'c{0}u{1}'.format(self.controller_id, self.id)

    @_check_initialised
    def get_info(self):
        '''
        Returns a dict with: type, device_name, status
        '''
        return {
            'controller_id': self.controller_id,
            'device_path': self.device_path,
            'id': self.id,
            'name': self.name,
            'physical_drives': [a.id for a in self.get_physical_drives()],
            'status': self.status,
            'type': self.type
        }

    @_check_initialised
    def get_physical_drives(self):
        '''
        Return a list of PhysicalDrive instances that form the logcal drive.
        '''
        # Find out what physical drive is being used by a logical drive
        res = run('omreport', 'storage pdisk controller={0} '
                  'vdisk={1}'.format(self.controller_id, self.id))
        if res.find('ArrayDisks') is None:
            raise exceptions.ControllerError("Unable to find which "
                                             "physical drive is being "
                                             "used by logical drive {0} "
                                             "on controller {1}".format(
                                             self.id, self.controller_id))
        physical_drives = []
        for entry in res.find('ArrayDisks'):
            physical_drive = _parse_physical_drive(entry, PhysicalDrive())
            physical_drives.append(physical_drive)
        return physical_drives

    @_check_initialised
    def delete(self):
        '''
        Delete the logical drive.

        :return: The information for the logical drive that just got deleted.
        '''
        info = self.get_info()
        res = run("omconfig", "storage vdisk controller={0} vdisk={1} "
                  "action=deletevdisk".format(self.controller_id,
                  self.id))
        _check_exit_code(res, "Failed to delete logical drive {0} on "
                              "controller {0}".format(self.controller_id,
                              self.id))
        info['status'] = 'Successfully removed'
        return info


class PhysicalDrive():
    def __init__(self, controller_id=None, pdisk_id=None):
        """
        Decide if the instance should be manually or automatically populated

        :param controller_id: The controller id
        :param pdisk_id: The pdisk id (usually something like 1:0:23)
        """
        if (controller_id is not None and pdisk_id is not None):
            res = run('omreport', 'storage pdisk controller={0} pdisk={1}'.format(
                      controller_id, pdisk_id))
            if res.find('ArrayDisks') is None:
                raise exceptions.ControllerError("Unable to retrieve information for "
                                           "physical drive {0} on controller "
                                           "{1}".format(pdisk_id, controller_id))
            entry = res.find('ArrayDisks')[0]
            self = _parse_physical_drive(entry, self)
            self.controller_id = controller_id
            self.id = pdisk_id

    @_check_initialised
    def get_info(self):
        '''
        Returns dict with: status, size, manufacturer, model, serial
        '''
        return {
            'controller_id': self.controller_id,
            'firmware': self.firmware,
            'id': self.id,
            'model': self.model,
            'serial': self.serial,
            'size': self.size,
            'state': self.state,
            'status': self.status
        }

    @_check_initialised
    def blink_led(self):
        '''
        Switch on the drive bay light, and returns success bool
        '''
        res = run('omconfig', 'storage pdisk action=blink controller={0} '
                  'pdisk={1}'.format(self.controller_id, self.id))
        _check_exit_code(res, "Unable to switch on the indicator LED for "
                              "physical drive {0} on controller {1}".format(
                              self.id, self.controller_id))
        return True

    @_check_initialised
    def unblink_led(self):
        '''
        Switch off the drive bay light, and returns success bool
        '''
        res = run('omconfig', 'storage pdisk action=unblink controller={0} '
                  'pdisk={1}'.format(self.controller_id, self.id))
        _check_exit_code(res, "Unable to switch off the indicator LED for "
                              "physical drive {0} on controller {1}".format(
                              self.id, self.controller_id))
        return True
