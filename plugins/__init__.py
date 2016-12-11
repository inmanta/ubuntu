"""
    Copyright 2016 Inmanta

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

    Contact: code@inmanta.com
"""

from inmanta.resources import Resource, resource, ResourceNotFoundExcpetion
from inmanta.agent.handler import provider, ResourceHandler
from inmanta.execute.util import Unknown

import re, logging, urllib

LOGGER = logging.getLogger(__name__)

@provider("std::Service", name = "ubuntu_service")
class UbuntuService(ResourceHandler):
    """
        A handler for services on systems that use upstart
    """
    def available(self, resource):
        return self._io.file_exists("/usr/lib/upstart") or self._io.file_exists("/usr/sbin/update-rc.d")

    def check_resource(self, resource):
        current = resource.clone()
        style = ""
        if self._io.file_exists("/etc/init/%s.conf" % resource.name):
            # new style (upstart)
            boot_config = self._io.run("/sbin/initctl", ["show-config", resource.name])[0]
            current.onboot = "start on " in boot_config


            exists = self._io.run("/sbin/status", [resource.name])
            if "start" in exists[0] or "running" in exists[0]:
                current.state = "running"
            else:
                current.state = "stopped"

            style = "upstart"

        elif self._io.file_exists("/etc/init.d/%s" % resource.name):
            # old style
            current.onboot = "already exist" in self._io.run("/usr/sbin/update-rc.d", ["-n", resource.name, "defaults"])[0]

            if self._io.run("/etc/init.d/%s" % resource.name, ["status"])[2] == 0:
                current.state = "running"
            else:
                current.state = "stopped"

            style = "init"
        else:
            raise ResourceNotFoundExcpetion("The %s service does not exist" % resource.name)

        return style, current

    def _list_changes(self, desired):
        style, current = self.check_resource(desired)
        changes = self._diff(current, desired)
        return style, changes

    def list_changes(self, desired):
        style, changes = self._list_changes(desired)
        return changes

    def can_reload(self):
        """
            Can this handler reload?
        """
        return True

    def do_reload(self, resource):
        """
            Reload this resource
        """
        self._io.run("/usr/sbin/service", [resource.name, "restart"])

    def do_changes(self, resource):
        style, changes = self._list_changes(resource)
        changed = False

        # update-rc.d foobar defaults
        # update-rc.d -f foobar remove

        if "state" in changes and changes["state"][0] != changes["state"][1]:
            action = "start"
            if changes["state"][1] == "stopped":
                action = "stop"

            # start or stop the service
            if style == "upstart":
                result = self._io.run("/sbin/%s" % action, [resource.name])
                if result[2] > 0:
                    raise Exception("Unable to %s %s: %s" % (action, resource.name, result[1]))

            elif style == "init":
                result = self._io.run("/etc/init.d/%s" % resource.name, [action])
                if result[2] > 0:
                    raise Exception("Unable to %s %s: %s" % (action, resource.name, result[1]))

            changed = True

        if "onboot" in changes and changes["onboot"][0] != changes["onboot"][1]:
            onboot = changes["onboot"][1]

            if style == "upstart":
                LOGGER.warn("Enabling or disabling boot for upstart jobs not supported")

            elif style == "init":
                if onboot:
                    self._io.run("/usr/sbin/update-rc.d", [resource.name, "defaults"])
                else:
                    self._io.run("/usr/sbin/update-rc.d", ["-f", resource.name, "remove"])

                changed = True

        return changed


