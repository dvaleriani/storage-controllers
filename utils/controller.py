# -*- coding: utf-8 -*-
#
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

'''
Module for managing storage controllers on POSIX-like systems.
'''
from salt.utils.decorators import depends

# Detect the controller from a list of supported models
models = {
    '10000079': 'perc8xx',
    '1000005b': 'perc8xx',
    '13c11004': 'lsi3ware'
}

with open('/proc/bus/pci/devices', 'r') as f:
    lines = f.readlines()
for line in lines:
    pci_id = line.split('\t')[1]
    if models.has_key(pci_id):
        model = models[pci_id]
        break

try:
    controller = getattr(__import__('storage_controllers.controllers',
                                    fromlist=[model]), model)
except ImportError:
    pass


def _fallback():
    return 'The storage-controllers module needs to be installed or missing ' \
           'controller plugin'

@depends('controller', fallback_function=_fallback)
def logical_drive(controller_id, logical_drive_id=None):
    """
    Provides information about logical drives.
    Returns only one logical drive if specified, otherwise returns information
    for all the logical drives of the specified controller.

    CLI Example:

    .. code-block:: bash

        salt '*' controller.logical_drive <controller id>
        salt '*' controller.logical_drive <controller id> <logical drive id>
    """
    if logical_drive_id is None:
        ctl = controller.Controller(controller_id)
        return [l.get_info() for l in ctl.get_logical_drives()]
    else:
        ld = controller.LogicalDrive(controller_id, logical_drive_id)
        return ld.get_info()

@depends('controller', fallback_function=_fallback)
def logical_drive_by_name(device_name):
    """
    Try to extract information for a logical drive given the device name.

    CLI Example:

    .. code-block:: bash

        salt '*' controller.logical_drive_by_name <device name>
    """
    try:
        return controller.get_logical_drive(device_name).get_info()
    except:
        return "Logical drive {0} not present".format(device_name)

@depends('controller', fallback_function=_fallback)
def logical_drive_delete(controller_id, logical_drive_id):
    """
    Delete a logical drive.
    Returns the information for the logical drive that just got deleted.

    CLI Example:

    .. code-block:: bash

        salt '*' controller.logical_drive_delete <controller id> <logical drive id>
    """
    try:
        return controller.LogicalDrive(controller_id, logical_drive_id).delete()
    except:
        return "Failed to delete logical drive {0} on controller {1}".format(
               logical_drive_id, controller_id)

@depends('controller', fallback_function=_fallback)
def logical_drive_create(controller_id, physical_drive_id):
    """
    Create a logical drive.
    Returns the information for the logical drive that just got created.

    CLI Example:

    .. code-block:: bash

        salt '*' controller.logical_drive_create <controller id> <physical drive>
    """
    try:
        ctl = controller.Controller(controller_id)
        return ctl.create_logical_drive(physical_drive_id)
    except:
        return ("Failed to create a logical drive with physical drive {0} "
                "on controller {1}".format(physical_drive_id, controller_id))

@depends('controller', fallback_function=_fallback)
def physical_drive(controller_id, physical_drive_id=None):
    """
    Provides information about physical drives.
    Returns only one physical drive if specified, otherwise returns information
    for all the physical drives of the specified controller.

    CLI Example:

    .. code-block:: bash

        salt '*' controller.physical_drive <controller id>
        salt '*' controller.physical_drive <controller id> <physical drive id>
    """
    if physical_drive_id is None:
        try:
            ctl = controller.Controller(controller_id)
            return [p.get_info() for p in ctl.get_physical_drives()]
        except:
            return ("Failed to get information for physical drives on "
                    "controller {0}".format(controller_id))
    else:
        try:
            phy_drv = controller.get_physical_drive(controller_id,
                                                    physical_drive_id)
            return phy_drv.get_info()
        except:
            return "Physical drive {0} on controller {1} not present".format(
                    physical_drive_id, controller_id)

@depends('controller', fallback_function=_fallback)
def info(controller_id=None):
    """
    Provides information about the storage controllers.
    Returns only one controller if specified, otherwise returns information
    for all the controllers on the server.

    CLI Example:

    .. code-block:: bash

        salt '*' controller.info
        salt '*' controller.info <controller id>
    """
    if controller_id is None:
        try:
            return [c.get_info() for c in controller.get_controllers()]
        except:
            return "Failed to get controllers information"
    else:
        try:
            return controller.Controller(controller_id).get_info()
        except:
            return "Failed to get information for controller {0}".format(
                   controller_id)
